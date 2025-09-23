from datetime import datetime

def parse_grams_time(s:str):
    # "150 13" -> (150.0, 13); "150" -> (150.0, current hour)
    s = s.replace(",", ".").strip()
    parts = s.split()
    grams = float(parts[0])
    if len(parts) > 1 and parts[1].isdigit():
        hh = int(parts[1])
    else:
        hh = datetime.now().hour
    return grams, hh
