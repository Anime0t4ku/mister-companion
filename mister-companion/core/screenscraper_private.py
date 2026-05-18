SS_DEV_ID = ""
SS_DEV_PASSWORD = ""
SS_SOFTNAME = "mister-companion"


def has_dev_credentials():
    return bool(SS_DEV_ID and SS_DEV_PASSWORD and SS_SOFTNAME)


def get_dev_credentials():
    if not has_dev_credentials():
        return None

    return {
        "devid": SS_DEV_ID,
        "devpassword": SS_DEV_PASSWORD,
        "softname": SS_SOFTNAME,
    }