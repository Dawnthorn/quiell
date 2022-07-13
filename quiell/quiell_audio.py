import asyncio
import logging
import signal
import sys
import traceback

from libqtile import bar
from libqtile.widget import base
from pypactl.controller import Controller



class SinkTile:
    def __init__(self, sink, text, enabled):
        self.sink = sink
        self.text = text
        self.enabled = enabled


    def __repr__(self):
        return f"<SinkTile text={self.text} enabled={self.enabled} sink={self.sink}>"



class QuiellAudio(base._TextBox, base.PaddingMixin):
    orientations = base.ORIENTATION_HORIZONTAL

    HEADPHONES_ICON = u"\U0001F50A"
    SPEAKERS_ICON = u"\U0001F3A7"
    TEXT_MAP = {
        "alsa_output.pci-0000_00_1b.0.analog-stereo": HEADPHONES_ICON,
        'alsa_output.usb-Sennheiser_Sennheiser_3D_G4ME1-00.analog-stereo': SPEAKERS_ICON,
    }

    def __init__(self, **config):
        base._TextBox.__init__(self, "  ", **config)
        self.add_defaults(base.PaddingMixin.defaults)
        self.logger = logging.getLogger('quala-audio')
        self.logger.addHandler(logging.FileHandler('/tmp/quala-audio.log'))
        self.logger.setLevel(logging.ERROR)
        self.logger.debug("__init__")
        self.sink_tiles = []
        self.border_width = 1


    @property
    def background_color(self):
        return self.background or self.bar.background


    def button_release(self, x, y, button):
        self.logger.debug(f"button_release({x}, {y}, {button})")
        sink_tile = self.sink_tile_at(x)
        self.logger.debug(f"sink_tile_at({x}): {sink_tile}")
        if sink_tile is None:
            return
        self.logger.debug(f"sink_default_set({sink_tile.sink.name})")
        self.qtile.call_soon(asyncio.create_task, self.pulse_audio.set_default_sink(sink_tile.sink.name))


    def calculate_length(self):
        length = 0
        for sink_tile in self.sink_tiles:
            length += self.sink_tile_width(sink_tile)
        return length


    async def _config_async(self):
        self.logger.debug("config_async")
        self.loop = asyncio.get_running_loop()
        self.pulse_audio = Controller(self.loop, logger=self.logger)
        await self.pulse_audio.start()
        await self.update_sinks()
        self.pulse_audio.subscribe(self.on_pypactl_event)
        self.logger.debug("exit config_async")


    def draw(self):
        if not self.can_draw():
            return
        self.drawer.clear(self.background_color)
        x = 0
        for sink_tile in self.sink_tiles:
            self.draw_sink_tile(sink_tile, x)
            x += self.sink_tile_width(sink_tile)
        self.drawer.draw(offsetx=self.offsetx, offsety=self.offsety, width=self.width)


    def draw_sink_tile(self, sink_tile, x):
        self.layout.text = sink_tile.text
        foreground = self.foreground
        if not sink_tile.enabled:
            foreground = self.background_color
        text_frame = self.layout.framed(self.border_width, foreground, self.padding_x, self.padding_y)
        text_frame.draw(x, 0)


    def finalize(self):
        self.logger.debug('finalize')
        self.transport.close()
        base._TextBox.finalize(self)
        self.logger.debug('finalize close')


    def on_pypactl_event(self, event):
        self.logger.debug(f"Event: {event}")
        method_name = f"on_pypactl_event_{event.facility.name.lower()}_{event.type.name.lower()}"
        method = getattr(self, method_name, None)
        if callable(method):
            self.qtile.call_soon(asyncio.create_task, method(event))


    async def on_pypactl_event_server_change(self, event):
        self.logger.debug(f"on_server_change {event}")
        await self.update_sinks()


    def sink_tile_at(self, x):
        check_x = 0
        for sink_tile in self.sink_tiles:
            sink_tile_width = self.sink_tile_width(sink_tile)
            self.logger.debug(f"x {x} check_x {check_x} sink_tile_width {sink_tile_width}")
            if x > check_x and x < check_x + sink_tile_width:
                return sink_tile
            check_x += sink_tile_width
        return None


    def sink_tile_width(self, sink_tile):
        text_width, text_height = self.drawer.max_layout_size(sink_tile.text, self.font, self.fontsize)
        return text_width + self.padding_x * 2 + self.border_width * 2


    async def update_sinks(self):
        server_info = await self.pulse_audio.server_info()
        sinks = await self.pulse_audio.sinks()
        self.sink_tiles = []
        for sink in sinks:
            text = self.TEXT_MAP.get(sink.name, None)
            if text is None:
                continue
            enabled = False
            if server_info.default_sink == sink.name:
                enabled = True
            sink_tile = SinkTile(sink, text, enabled)
            self.sink_tiles.append(sink_tile)
        self.logger.debug("Sink Tiles: {}".format(self.sink_tiles))
        self.draw()
