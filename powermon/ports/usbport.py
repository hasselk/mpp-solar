import logging
import os
import time

from powermon.dto.portDTO import PortDTO
from powermon.commands.result import Result
from powermon.ports.abstractport import AbstractPort
from powermon.protocols import get_protocol_definition
from powermon.commands.command import Command

log = logging.getLogger("USBPort")


class USBPort(AbstractPort):
    @classmethod
    def fromConfig(cls, config=None):
        log.debug(f"building usb port. config:{config}")
        path = config.get("path", "/dev/hidraw0")
        # get protocol handler, default to PI30 if not supplied
        protocol = get_protocol_definition(protocol=config.get("protocol", "PI30"))
        return cls(path=path, protocol=protocol)

    def __init__(self, path, protocol) -> None:
        super().__init__(protocol=protocol)
        self.path = path

    def toDTO(self):
        dto = PortDTO(type="usb", path=self.path, protocol=self.get_protocol().toDTO())
        return dto

    def connect(self) -> int:
        log.debug(f"USBPort connecting. path:{self.path}, protocol: {self.get_protocol()}")
        try:
            self.port = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
            log.debug(f"USBPort port number ${self.port}")
        except Exception as e:
            log.warning(f"Error openning usb port: {e}")
            self.error = e
        return self.port

    def disconnect(self) -> None:
        log.debug(f"USBPort disconnecting {self.port}")
        if self.port is not None:
            os.close(self.port)
        return

    def send_and_receive(self, command: Command) -> Result:
        response_line = bytes()
        result = Result(command_code=command.code)

        # Open USB device
        usb0 = None
        try:
            usb0 = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except Exception as e:
            log.error("USB open error: {}".format(e))
            result.error = True
            result.error_messages.append("USB open error: {}".format(e))
            return result

        # Send the command to the open usb connection
        full_command = command.get_full_command()
        cmd_len = len(full_command)
        log.debug(f"length of to_send: {cmd_len}")
        # for command of len < 8 it ok just to send
        # otherwise need to pack to a multiple of 8 bytes and send 8 at a time
        if cmd_len <= 8:
            # Send all at once
            log.debug("sending full_command in on shot")
            time.sleep(0.05)
            os.write(usb0, full_command)
        else:
            log.debug("multiple chunk send")
            chunks = [full_command[i:i + 8] for i in range(0, cmd_len, 8)]
            for chunk in chunks:
                # pad chunk to 8 bytes
                if len(chunk) < 8:
                    padding = 8 - len(chunk)
                    chunk += b'\x00' * padding
                log.debug("sending chunk: %s" % (chunk))
                time.sleep(0.05)
                os.write(usb0, chunk)
        time.sleep(0.25)
        # Read from the usb connection
        # try to a max of 100 times
        for x in range(100):
            # attempt to deal with resource busy and other failures to read
            try:
                time.sleep(0.15)
                r = os.read(usb0, 256)
                response_line += r
            except Exception as e:
                log.debug("USB read error: {}".format(e))
            # Finished is \r is in byte_response
            if bytes([13]) in response_line:
                # remove anything after the \r
                response_line = response_line[: response_line.find(bytes([13])) + 1]
                break
        log.debug("usb response was: %s", response_line)
        result.raw_response = response_line
        os.close(usb0)
        return result
