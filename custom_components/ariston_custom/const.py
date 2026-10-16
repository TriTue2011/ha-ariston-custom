"""Hằng số cho integration Ariston Custom (dịch ngược từ APK Ariston NET)."""

from datetime import timedelta

DOMAIN = "ariston_custom"

CONF_GW = "gateway"
CONF_WHE_TYPE = "whe_type"

# API cloud Ariston (theo re-api-spec.md)
API_BASE = "https://www.ariston-net.remotethermo.com/api"
AUTH_HEADER = "ar.authToken"  # KHÔNG phải Authorization: Bearer
UM_SYS = "si"  # metric / °C

# eSlpPlantMode
PLANT_MODE_PROGRAM = 1
PLANT_MODE_MANUAL = 2
PLANT_MODE_NAMES = {
    PLANT_MODE_PROGRAM: "program",
    PLANT_MODE_MANUAL: "manual",
}

# eSlpOperativeMode
OPERATIVE_MODES = {
    0: "green",
    1: "comfort",
    2: "fast",
    3: "auto",
    4: "hchp",
    5: "electric",
    6: "greenplus",
}

# eWheTypeDto (theo python-ariston-api)
WHE_TYPE_LYDOS = 3
WHE_TYPE_SLP = 4
WHE_TYPES_HO_TRO = (WHE_TYPE_LYDOS, WHE_TYPE_SLP)

# PlantData cho từng loại
PLANT_DATA_MED = "medPlantData"  # Lydos (3)
PLANT_DATA_SLP = "slpPlantData"  # SLP (4)

# LuxPlantMode cho Lydos (3) — theo python-ariston-api
LYDOS_MODE_MANUAL = 1
LYDOS_MODE_PROGRAM = 5
LYDOS_MODE_BOOST = 9
LYDOS_MODES = {
    LYDOS_MODE_MANUAL: "manual",
    LYDOS_MODE_PROGRAM: "program",
    LYDOS_MODE_BOOST: "boost",
}

# eEnergyUsageDto cho bình điện trở
ENERGY_USAGE_SLP = "DhwResistorElec"

# Poll
SCAN_INTERVAL_STATE = timedelta(seconds=60)
SCAN_INTERVAL_ENERGY = timedelta(minutes=30)
SCAN_INTERVAL_SETTINGS = timedelta(minutes=5)
SCAN_INTERVAL_SCHEDULE = timedelta(minutes=15)

# Keys plantSettings cho Lydos (medPlantData)
SETTING_LEGIONELLA = "MedAntilegionellaOnOff"
SETTING_MAX_TEMP = "MedMaxSetpointTemperature"

# Giới hạn nhiệt độ SLP (plantSettings id 28/25)
MIN_TEMP = 40.0
MAX_TEMP = 80.0
