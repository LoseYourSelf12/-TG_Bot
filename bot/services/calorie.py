def mifflin_st_jeor(sex:str, weight:float, height_cm:int, age:int) -> float:
    base = 10*weight + 6.25*height_cm - 5*age
    return base + (5 if sex == "male" else -161)

def tdee(bmr:float, activity:str) -> float:
    factors = {"sedentary":1.2,"light":1.375,"moderate":1.55,"high":1.725,"athlete":1.9}
    return bmr * factors.get(activity, 1.2)
