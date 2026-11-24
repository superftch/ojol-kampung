import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.dom import minidom


class SvgCaptchaSolver:
    model = "eyJNTExRTExRTExRTExMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTExRTExRWk1MTFFMTFFMTFFMTFFaIjogIjAiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTFoiOiAiMSIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExMUUxMTFFMTFFaIjogIjIiLCAiTUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExMUUxMUUxMUUxMUUxMUUxMUUxMTExRTExRTExRTExRTExRTExRTExMTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiMyIsICJNTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRWk1MTFFMTExRTExRTExRTExRTExRTExRTExMUUxMTFFMTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRWiI6ICI0IiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMTExMUUxMTFFMTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTExRTExRTExRTExRTExRWiI6ICI1IiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIjYiLCAiTUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFaTUxMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMTExRTExRTExRTExRTExRTExMUUxMTFFMTFFMTFFMTExRWiI6ICI3IiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExMUUxMUUxMUUxMUUxMTExMUUxMUUxMUUxMUUxMTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExMUUxMUUxMUUxMUUxMUUxMUVoiOiAiOCIsICJNTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIjkiLCAiTUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExMUUxMUUxMUUxMUUxMUUxMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTExRWiI6ICJBIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUVpNTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExMUUxMTExMUUxMTFFMTFFMTFFMTFFMTFFMTFFaIjogIkIiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiQyIsICJNTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIkQiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIkUiLCAiTUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUVoiOiAiRiIsICJNTExRTExRTExRTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMWiI6ICJHIiwgIk1MTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJIIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAibCIsICJNTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJKIiwgIk1MTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMTExMUVpNTExRTExRTExRTExMUUxMUUxMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJLIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiTCIsICJNTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRWiI6ICJNIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMWk1MTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiTiIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJPIiwgIk1MTFFMTFFMTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFaIjogIlAiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTExRTExMUUxMUUxMUUxMUUxMUVpNTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTExMTFFMTFFMTFFaIjogIlEiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMTFFMTFFMTFFaTUxMTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFaTUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIlIiLCAiTUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiUyIsICJNTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJUIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIlUiLCAiTUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogIlYiLCAiTUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiVyIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFaIjogIlgiLCAiTUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFoiOiAiWSIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMTFFMTFFMTFFMTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRWiI6ICJaIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRWk1MTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogImEiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRWiI6ICJiIiwgIk1MTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExMUUxMUUxMUVoiOiAiYyIsICJNTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiZCIsICJNTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTExRWk1MTFFMTFFMTFFMTFFMTFFaTUxMUUxMTExRTExRTExRWiI6ICJlIiwgIk1MTFFMTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFaTUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExMUUxMTExRTExRTExMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogImYiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMTFFMTExRTExRTExRTExMUUxMUUxMUUxMUUxMTExRTExRTExRTExRTExRTExMUUxMTFFMTFFMTExRTExMUVpNTExRTExRTExRTExRTExRTExRTExRTExRWiI6ICJnIiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExMUUxMUVoiOiAiaCIsICJNTExRTExMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTFpNTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExMTFFMTFFMTFFMTFFMTFFMTFFMTFFaIjogImkiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExMUUxMUUxMUUxMUUxMUUxMTFFMTExMUUxMUVpNTExMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiaiIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAiayIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTExRTExRWk1MTExaIjogIm0iLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVpNTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAibiIsICJNTExRTExRTExRTExRTExRTExRTExRWk1MTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAibyIsICJNTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExMUUxMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMTExMUUxMTFFMTFFMTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxaTUxMUUxMUUxMUUxMUUxMTFFMTExRTExMUUxMUVoiOiAicCIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFaTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAicSIsICJNTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUVpNTExRTExRTExRTExRTExRTExRTExMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExaTUxMTFoiOiAiciIsICJNTExMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMTExRTExRTExRTExMUUxMUVoiOiAicyIsImV4dGVuc2lvbl9vcmlnaW5hbF9hdXRob3IiOiJzdXNocnV0MTExIiwgIk1MTFFMTFFMTFFMTFFMTExRTExRTExRTExMUUxMUUxMUUxMUUxMUVpNTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTExRTExRTExRTExRTExRTExRTExRTExMUUxMTFFMTFFMTFFaIjogInQiLCAiTUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExMTExRTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAidSIsICJNTExRTExRTExRTExRTExRTExRTExRTExRWk1MTFFMTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMTFFMTExRWiI6ICJ2IiwgIk1MTFFMTExRTExRTExRTExRTExRTExRTExRTExRTExRTExMUUxMUUxMUUxMUUxMUUxMTFFaTUxMUUxMUUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTExRTExMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExaIjogInciLCAiTUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFaTUxMUUxMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExMUVoiOiAieCIsICJNTExRTExRTExRTExRTExRTExRTExRTExMUUxMUVpNTExRTExMUUxMUUxMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRWiI6ICJ5IiwgIk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExRTExRTExRTExRTExRWk1MTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTFFMTExRTExMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUUxMUVoiOiAieiJ9"

    def solve_captcha(self, svg_captcha_file):
        with open(svg_captcha_file, mode="r") as file:
            lines = file.readline()
        svg_captcha = lines

        parsed_model = dict(json.loads(base64.b64decode(self.model)))
        element = minidom.parseString(svg_captcha)
        paths = element.getElementsByTagName("path")

        nostroke_paths = [path for path in paths if len(path.getAttribute("stroke")) == 0]

        vals = [int(p.getAttribute("d").split(".")[0].replace("M", "")) for p in nostroke_paths]
        sorted_vals = sorted(vals)
        solution = [""] * len(nostroke_paths)
        for i, path in enumerate(nostroke_paths):
            pattern = re.sub(r"[\d.\s]*", "", path.getAttribute("d"))
            solution[sorted_vals.index(vals[i])] = parsed_model[pattern]

        return "".join(solution)


# ponytail: port of AmireNoori/SVG-Captcha-Solver (MIT); works only on SVG captchas.
def solve_svg_captcha(svg_text: str) -> str:
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as handle:
        handle.write(svg_text)
        path = handle.name
    try:
        return SvgCaptchaSolver().solve_captcha(path)
    finally:
        Path(path).unlink(missing_ok=True)


class SvgCaptchaSolverError(ValueError):
    """Gambar cek tidak dapat dipecahkan oleh model svg-captcha."""


# ponytail: polyline captcha solver — normalisasi bentuk + template bank yang tumbuh sendiri.
# Bank dibangun dari digit yang sudah dikonfirmasi server (klaim ongkir sukses), jadi bentuk
# font baru otomatis dikenali pada kemunculan berikutnya. Tanpa dependensi eksternal.
_SEED = {
    "8": [
        [
            [(0.053, 0.0), (0.898, 0.056), (1.0, 1.0), (0.079, 0.98), (0.0, 0.01)],
            [(0.0, 0.0), (0.078, 1.0), (1.0, 0.931), (0.944, 0.005)],
        ]
    ],
    "0": [[[(0.05, 0.0), (0.94, 0.003), (1.0, 0.945), (0.14, 1.0), (0.0, 0.003)]]],
    "5": [[[(0.91, 0.03), (0.0, 0.0), (0.05, 0.41), (0.95, 0.45), (1.0, 0.96), (0.07, 1.0)]]],
    "3": [[[(0.0, 0.0), (0.93, 0.01), (0.39, 0.47), (1.0, 0.58), (0.93, 1.0), (0.0, 0.97)]]],
    "2": [[[(0.0, 0.16), (0.25, 0.0), (0.89, 0.05), (0.91, 0.50), (0.09, 1.0), (1.0, 0.99)]]],
    "6": [[[(1.0, 0.0), (0.05, 0.4), (0.0, 1.0), (1.0, 1.0), (1.0, 0.48), (0.05, 0.49)]]],
    "7": [[[(0.0, 0.0), (1.0, 0.01), (0.22, 1.0)]]],
    # 9: kotak atas + ekor diagonal ke kiri bawah (dikonfirmasi server 20 Nov 2026).
    "9": [[[(1.0, 0.62), (0.35, 0.63), (0.33, 0.16), (1.0, 0.13), (0.93, 0.63), (0.0, 1.0)]]],
}
_SWITCH = 0.16  # sama-digit<=0.15, beda digit>=0.17 pada sampel live


def _resample(points, count=24):
    """Titik merata sepanjang polyline agar jarak antar bentuk tak bergantung jumlah titik."""
    if len(points) < 2:
        return list(points) * count
    lengths = [0.0]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        lengths.append(lengths[-1] + ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
    total = lengths[-1] or 1.0
    out = []
    for step in range(count):
        target = total * step / (count - 1)
        index = 0
        for i in range(len(lengths) - 1):
            if lengths[i] <= target <= lengths[i + 1]:
                index = i
                break
        else:
            index = len(points) - 2
        span = lengths[index + 1] - lengths[index] or 1.0
        ratio = min(1.0, max(0.0, (target - lengths[index]) / span))
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        out.append((x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio))
    return out


def _normalize(glyph):
    xs = [x for stroke in glyph for x, _ in stroke]
    ys = [y for stroke in glyph for _, y in stroke]
    width = max(xs) - min(xs) or 1.0
    height = max(ys) - min(ys) or 1.0
    return [
        _resample([((x - min(xs)) / width, (y - min(ys)) / height) for x, y in stroke])
        for stroke in glyph
    ]


def _stroke_distance(a, b):
    """Jarak dua stroke: cocokkan urutan titik (boleh terbalik/bergeser fase)."""
    count = len(a)
    if len(b) != count:
        return 1.0
    best = 1.0
    is_closed = ((b[0][0] - b[-1][0]) ** 2 + (b[0][1] - b[-1][1]) ** 2) ** 0.5 < 0.15
    candidates = [b, b[::-1]]
    if is_closed:
        for cand in candidates:
            for shift in range(count):
                shifted = cand[shift:] + cand[:shift]
                cost = (
                    sum(((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 for (x1, y1), (x2, y2) in zip(a, shifted))
                    / count
                )
                best = min(best, cost)
    else:
        for cand in candidates:
            cost = (
                sum(((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 for (x1, y1), (x2, y2) in zip(a, cand))
                / count
            )
            best = min(best, cost)
    return best


def _shape_distance(a, b):
    """Jarak bentuk dua glyph (semua stroke dinormalisasi), cocokkan stroke termurah."""
    if len(a) != len(b):
        return 1.0
    remaining = list(b)
    total = 0.0
    for stroke in a:
        costs = [
            (min(_stroke_distance(stroke, other), _stroke_distance(other, stroke)), index)
            for index, other in enumerate(remaining)
        ]
        cost, index = min(costs)
        total += cost / 2
        remaining.pop(index)
    return total / len(a)


def _bank_path(directory):
    return Path(directory) / "cek-templates.json"


def _extract_glyph(shape):
    if isinstance(shape, dict):
        return shape.get("glyph", [])
    return shape


def load_bank(directory=None):
    seeds = {
        digit: [list([list(p) for p in stroke] for stroke in variant) for variant in variants]
        for digit, variants in _SEED.items()
    }
    repo_bank = Path(__file__).resolve().parent.parent / "assets" / "cek-templates.json"
    stored = {}
    if repo_bank.is_file():
        try:
            loaded = json.loads(repo_bank.read_text())
            if isinstance(loaded, dict):
                stored.update(loaded)
        except (OSError, ValueError):
            pass
    if directory and _bank_path(directory).is_file():
        try:
            loaded = json.loads(_bank_path(directory).read_text())
            if isinstance(loaded, dict):
                stored.update(loaded)
        except (OSError, ValueError):
            pass
    for digit, variants in seeds.items():
        stored.setdefault(digit, variants)
    return stored


def save_bank(directory, bank):
    dirs = [directory] if isinstance(directory, (str, Path)) else list(directory or [])
    for d in dirs:
        try:
            if d:
                path = Path(d) / "cek-templates.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(bank))
        except OSError:
            pass
    if os.environ.get("OJOL_ENV") != "testing":
        try:
            repo_bank = Path(__file__).resolve().parent.parent / "assets" / "cek-templates.json"
            repo_bank.parent.mkdir(parents=True, exist_ok=True)
            repo_bank.write_text(json.dumps(bank))
        except OSError:
            pass


def get_bank_templates(directory=None):
    return load_bank(directory)


def save_template_to_bank(directory, digit: str, glyph: list, contributed_by: str = None):
    """Menyimpan varian bentuk glyph baru ke bank digit tertentu (bisa untuk satu atau multi-direktori)."""
    digit = str(digit).strip()
    if len(digit) != 1 or not digit.isdigit():
        raise ValueError("Digit harus berupa karakter angka 0-9")
    if not isinstance(glyph, list) or not glyph:
        raise ValueError("Data glyph tidak valid")

    dirs = [directory] if isinstance(directory, (str, Path)) else list(directory or [])
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    cleaned_glyph = [[list(p) for p in stroke] for stroke in glyph if isinstance(stroke, list)]
    if not cleaned_glyph:
        raise ValueError("Data stroke glyph kosong")

    norm_new = _normalize(cleaned_glyph)
    shapes = bank.get(digit, [])
    # Hindari duplikat jika bentuknya sangat mirip (< 0.08)
    is_dup = any(
        _shape_distance(norm_new, _normalize([[tuple(p) for p in s] for s in _extract_glyph(shape)])) < (_SWITCH * 0.5)
        for shape in shapes
    )
    if not is_dup:
        entry = (
            {
                "glyph": cleaned_glyph,
                "by": str(contributed_by).strip(),
                "at": datetime.now(timezone.utc).isoformat(),
            }
            if contributed_by
            else cleaned_glyph
        )
        bank.setdefault(digit, []).append(entry)
        save_bank(dirs, bank)
    return bank


def delete_template_from_bank(directory, digit: str, index: int):
    """Menghapus varian bentuk dari bank digit tertentu."""
    digit = str(digit).strip()
    dirs = [directory] if isinstance(directory, (str, Path)) else list(directory or [])
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    if digit in bank and 0 <= index < len(bank[digit]):
        bank[digit].pop(index)
        save_bank(dirs, bank)
    return bank


def record_unknown_glyph(directory, glyph, normalized, trip_id=None, svg_text=None):
    """Menyimpan glyph yang belum dikenali ke antrean review."""
    if not directory:
        return None
    try:
        rev_id = f"REV-{uuid4().hex[:10].upper()}"
        rev_dir = Path(directory) / "cek-reviews"
        rev_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = {
            "id": rev_id,
            "time": datetime.now(timezone.utc).isoformat(),
            "trip_id": trip_id,
            "raw_glyph": [[list(p) for p in stroke] for stroke in glyph],
            "normalized_glyph": normalized,
            "status": "pending",
        }
        if svg_text:
            data["svg_text"] = svg_text
        (rev_dir / f"{rev_id}.json").write_text(json.dumps(data, indent=2))
        return rev_id
    except OSError:
        return None


def get_pending_reviews(directory, account_name=None):
    """Mengambil semua glyph yang belum dikenali untuk direview user."""
    if not directory:
        return []
    path = Path(directory)
    resolved_file = path / "cek-reviews-resolved.json"
    resolved_ids = set()
    if resolved_file.is_file():
        try:
            resolved_ids = set(json.loads(resolved_file.read_text()))
        except (ValueError, OSError):
            resolved_ids = set()

    reviews = []
    seen_ids = set()

    # Muat cache sampel SVG dari direktori cek-samples untuk mencocokkan gambar asli game
    samples_dir = path / "cek-samples"
    samples_cache = []
    if samples_dir.is_dir():
        for s_file in sorted(samples_dir.glob("*.svg"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                content = s_file.read_text().strip()
                if content.startswith("<svg"):
                    samples_cache.append((s_file.stem, content))
            except OSError:
                pass

    def find_matching_svg(target_glyph, trip_id=None):
        if trip_id:
            for stem, c in samples_cache:
                if stem == trip_id:
                    return c
        try:
            norm_target = _normalize(target_glyph)
            for _, sample_svg in samples_cache:
                for s_glyph in _glyphs(sample_svg):
                    if _shape_distance(norm_target, _normalize(s_glyph)) < 0.08:
                        return sample_svg
        except Exception:
            pass
        return None

    # 1. Dari cek-reviews
    rev_dir = path / "cek-reviews"
    if rev_dir.is_dir():
        for file in sorted(rev_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            if file.stem in resolved_ids:
                continue
            try:
                data = json.loads(file.read_text())
                if isinstance(data, dict) and data.get("status") == "pending":
                    glyph = data.get("normalized_glyph") or data.get("raw_glyph")
                    rid = data.get("id") or file.stem
                    if glyph and rid not in seen_ids:
                        svg_text = data.get("svg_text") or find_matching_svg(glyph, data.get("trip_id"))
                        reviews.append({
                            "id": rid,
                            "error_id": data.get("error_id"),
                            "trip_id": data.get("trip_id"),
                            "time": data.get("time"),
                            "glyph": glyph,
                            "svg_text": svg_text,
                            "account_name": account_name or data.get("account_name"),
                        })
                        seen_ids.add(rid)
            except (ValueError, OSError):
                continue

    # 2. Dari errors/OJL-*.json
    err_dir = path / "errors"
    if err_dir.is_dir():
        for file in sorted(err_dir.glob("OJL-*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            err_id = file.stem
            rev_err_id = f"rev-err-{err_id}"
            if err_id in resolved_ids or rev_err_id in resolved_ids or err_id in seen_ids:
                continue
            try:
                data = json.loads(file.read_text())
                msg = str(data.get("message") or "")
                if "Glyph cek belum dikenali" in msg or data.get("category") == "SvgCaptchaSolverError":
                    match = re.search(r"Glyph cek belum dikenali:\s*(\[\[\[.*?\]\]\])", msg)
                    if match:
                        glyph = json.loads(match.group(1))
                        # Deduplikasi: bila review untuk trip_id atau bentuk glyph ini sudah tercatat dari cek-reviews,
                        # cukup tautkan error_id ke review tersebut agar tidak muncul kartu duplikat.
                        norm_g = _normalize(glyph)
                        existing_rev = None
                        for r in reviews:
                            if data.get("trip_id") and r.get("trip_id") == data.get("trip_id"):
                                existing_rev = r
                                break
                            if _shape_distance(norm_g, _normalize(r.get("glyph", []))) < 0.05:
                                existing_rev = r
                                break
                        if existing_rev:
                            if not existing_rev.get("error_id"):
                                existing_rev["error_id"] = err_id
                            seen_ids.add(err_id)
                            seen_ids.add(rev_err_id)
                            continue

                        svg_text = find_matching_svg(glyph, data.get("trip_id"))
                        reviews.append({
                            "id": rev_err_id,
                            "error_id": err_id,
                            "trip_id": data.get("trip_id"),
                            "time": data.get("time"),
                            "glyph": glyph,
                            "svg_text": svg_text,
                            "account_name": account_name or data.get("account_name"),
                        })
                        seen_ids.add(err_id)
                        seen_ids.add(rev_err_id)
            except Exception:
                continue

    return reviews


def get_all_pending_reviews(directories, account_names=None):
    """Mengumpulkan antrean review captcha gagal dari semua akun armada yang terdaftar."""
    dirs = [directories] if isinstance(directories, (str, Path)) else list(directories or [])
    account_names = account_names or {}
    all_reviews = []
    seen_ids = set()

    for d in dirs:
        if not d:
            continue
        p = Path(d)
        acc_name = account_names.get(str(p)) or account_names.get(p.name) or account_names.get(p.stem)
        reviews = get_pending_reviews(p, account_name=acc_name)
        for r in reviews:
            rid = r.get("id") or r.get("error_id")
            if not rid or rid in seen_ids:
                continue
            # Deduplikasi lintas armada jika bentuk glyph sama (< 0.04) atau trip_id sama
            norm_r = _normalize(r.get("glyph", []))
            existing_cross = None
            for ex in all_reviews:
                if ex.get("trip_id") and r.get("trip_id") and ex.get("trip_id") == r.get("trip_id"):
                    existing_cross = ex
                    break
                if _shape_distance(norm_r, _normalize(ex.get("glyph", []))) < 0.04:
                    existing_cross = ex
                    break
            if existing_cross:
                if r.get("account_name") and r["account_name"] not in (existing_cross.get("account_name") or ""):
                    existing_cross["account_name"] = f"{existing_cross.get('account_name', '')}, {r['account_name']}".strip(", ")
                seen_ids.add(rid)
                continue

            seen_ids.add(rid)
            all_reviews.append(r)

    all_reviews.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    return all_reviews


def resolve_review(directory, review_id: str, digit: str = None, glyph: list = None, resolved_by: str = None):
    """Menandai review selesai dan menambahkan ke bank angka bila digit & glyph diberikan (bisa multi-direktori)."""
    if not directory:
        return
    dirs = [directory] if isinstance(directory, (str, Path)) else list(directory or [])
    if digit and glyph:
        save_template_to_bank(dirs, digit, glyph, contributed_by=resolved_by)

    for d in dirs:
        if not d:
            continue
        path = Path(d)
        resolved_file = path / "cek-reviews-resolved.json"
        resolved_ids = set()
        if resolved_file.is_file():
            try:
                resolved_ids = set(json.loads(resolved_file.read_text()))
            except (ValueError, OSError):
                resolved_ids = set()

        resolved_ids.add(review_id)
        if "OJL-" in review_id:
            match = re.search(r"OJL-[0-9A-F]{12}", review_id)
            if match:
                resolved_ids.add(match.group(0))
                resolved_ids.add(f"rev-err-{match.group(0)}")

        # Bersihkan file cek-reviews/*.json yang relevan
        rev_dir = path / "cek-reviews"
        if rev_dir.is_dir():
            for rf in rev_dir.glob("*.json"):
                if rf.stem == review_id:
                    resolved_ids.add(rf.stem)
                    try:
                        data = json.loads(rf.read_text())
                        data["status"] = "resolved"
                        data["resolved_digit"] = digit
                        if resolved_by:
                            data["resolved_by"] = resolved_by
                        rf.write_text(json.dumps(data, indent=2))
                    except (ValueError, OSError):
                        pass
                elif glyph:
                    try:
                        data = json.loads(rf.read_text())
                        g = data.get("normalized_glyph") or data.get("raw_glyph")
                        if g and _shape_distance(_normalize(glyph), _normalize(g)) < 0.05:
                            resolved_ids.add(rf.stem)
                            data["status"] = "resolved"
                            data["resolved_digit"] = digit
                            if resolved_by:
                                data["resolved_by"] = resolved_by
                            rf.write_text(json.dumps(data, indent=2))
                    except Exception:
                        pass

        # Bersihkan juga error ID yang terkait glyph yang sama dari daftar pending
        if glyph:
            err_dir = path / "errors"
            if err_dir.is_dir():
                for ef in err_dir.glob("OJL-*.json"):
                    try:
                        edata = json.loads(ef.read_text())
                        emsg = str(edata.get("message") or "")
                        ematch = re.search(r"Glyph cek belum dikenali:\s*(\[\[\[.*?\]\]\])", emsg)
                        if ematch:
                            eglyph = json.loads(ematch.group(1))
                            if _shape_distance(_normalize(glyph), _normalize(eglyph)) < 0.05:
                                resolved_ids.add(ef.stem)
                                resolved_ids.add(f"rev-err-{ef.stem}")
                    except Exception:
                        pass

        try:
            resolved_file.write_text(json.dumps(list(resolved_ids), indent=2))
        except OSError:
            pass


def dismiss_review(directory, review_id: str, glyph: list = None):
    """Mengabaikan review tanpa menyimpan ke bank angka."""
    resolve_review(directory, review_id, digit=None, glyph=glyph)


def learn_polyline(directory, svg_text, code, contributed_by=None):
    """Simpan bentuk glyph yang baru saja dikonfirmasi server untuk digit yang sesuai."""
    glyphs = _glyphs(svg_text)
    if len(glyphs) != len(code):
        return
    dirs = [directory] if isinstance(directory, (str, Path)) else list(directory or [])
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    changed = False
    for digit, glyph in zip(code, glyphs):
        shapes = bank.get(digit, [])
        normalized = _normalize(glyph)
        if all(
            _shape_distance(normalized, _normalize([[tuple(p) for p in s] for s in _extract_glyph(shape)]))
            > _SWITCH * 0.9
            for shape in shapes
        ):
            cleaned = [[list(p) for p in stroke] for stroke in glyph]
            entry = (
                {"glyph": cleaned, "by": contributed_by, "at": datetime.now(timezone.utc).isoformat()}
                if contributed_by
                else cleaned
            )
            bank.setdefault(digit, []).append(entry)
            changed = True
    if changed:
        save_bank(dirs, bank)


def _glyphs(svg_text):
    import re as _re

    polys = [
        [(float(a), float(b)) for a, b in _re.findall(r"(-?[\d.]+),(-?[\d.]+)", row)]
        for row in _re.findall(r'<polyline points="([^"]+)"', svg_text)
    ]
    if not polys:
        raise SvgCaptchaSolverError("SVG cek tidak berisi polyline digit")
    polys.sort(key=lambda pts: min(x for x, _ in pts))
    glyphs = []
    for pts in polys:
        left = min(x for x, _ in pts)
        if glyphs and left - max(x for g in glyphs for stroke in g for x, _ in stroke) > 14:
            glyphs.append([pts])
        elif glyphs:
            glyphs[-1].append(pts)
        else:
            glyphs.append([pts])
    return glyphs


def solve_polyline_captcha(svg_text, directory=None, trip_id=None):
    bank = load_bank(directory)
    result = []
    unknowns = []
    for glyph in _glyphs(svg_text):
        normalized = _normalize(glyph)
        xs = [x for stroke in glyph for x, _ in stroke]
        ys = [y for stroke in glyph for _, y in stroke]
        best_digit, best_cost = None, _SWITCH
        # 0 harus tertutup; 9 mirip 0 tapi ada ekor (ujung terbuka).
        closed = (
            (
                (normalized[0][0][0] - normalized[0][-1][0]) ** 2
                + (normalized[0][0][1] - normalized[0][-1][1]) ** 2
            )
            ** 0.5
            < 0.15
            if normalized
            else True
        )
        for digit, variants in bank.items():
            if digit == "0" and not closed:
                continue
            for shape in variants:
                raw_shape = _extract_glyph(shape)
                cost = _shape_distance(
                    normalized, _normalize([[tuple(p) for p in s] for s in raw_shape])
                )
                if cost < best_cost:
                    best_digit, best_cost = digit, cost
        if (
            best_digit is None
            and len(glyph) == 1
            and (max(xs) - min(xs)) / ((max(ys) - min(ys)) or 1.0) < 0.5
        ):
            best_digit = "1"  # digit sempit hampir pasti 1
        if best_digit is None:
            unknowns.append((glyph, normalized))
        else:
            result.append(best_digit)

    if unknowns:
        if directory:
            for g, norm in unknowns:
                record_unknown_glyph(directory, g, norm, trip_id=trip_id, svg_text=svg_text)
        first_norm = unknowns[0][1]
        raise SvgCaptchaSolverError(
            "Glyph cek belum dikenali: " + json.dumps(first_norm, default=list)
        )
    return "".join(result)
