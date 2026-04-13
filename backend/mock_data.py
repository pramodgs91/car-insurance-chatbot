"""
Mock data for 100 car make/model/variants, insurers, add-ons, and pricing.
"""
import random
import hashlib

# ── 100 Car Make / Model / Variants ──────────────────────────────────────────

CAR_DATABASE = [
    # Maruti Suzuki
    {"make": "Maruti Suzuki", "model": "Swift", "variant": "VXi 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "Swift", "variant": "ZXi+ 1.2L Petrol AMT", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "Baleno", "variant": "Delta 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "Baleno", "variant": "Alpha 1.2L Petrol CVT", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "Alto K10", "variant": "VXi 1.0L Petrol", "cc": 998, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "WagonR", "variant": "ZXi 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "WagonR", "variant": "ZXi+ 1.2L Petrol AGS", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Maruti Suzuki", "model": "Ertiga", "variant": "VXi 1.5L Petrol", "cc": 1462, "fuel": "Petrol", "segment": "mpv"},
    {"make": "Maruti Suzuki", "model": "Ertiga", "variant": "ZXi+ 1.5L Petrol AT", "cc": 1462, "fuel": "Petrol", "segment": "mpv"},
    {"make": "Maruti Suzuki", "model": "Brezza", "variant": "ZXi 1.5L Petrol", "cc": 1462, "fuel": "Petrol", "segment": "suv"},
    {"make": "Maruti Suzuki", "model": "Brezza", "variant": "ZXi+ 1.5L Petrol AT", "cc": 1462, "fuel": "Petrol", "segment": "suv"},
    {"make": "Maruti Suzuki", "model": "Grand Vitara", "variant": "Alpha 1.5L Hybrid", "cc": 1462, "fuel": "Hybrid", "segment": "suv"},
    {"make": "Maruti Suzuki", "model": "Dzire", "variant": "ZXi 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Maruti Suzuki", "model": "Fronx", "variant": "Delta+ 1.0L Turbo", "cc": 998, "fuel": "Petrol", "segment": "suv"},
    {"make": "Maruti Suzuki", "model": "Jimny", "variant": "Alpha 1.5L Petrol AT", "cc": 1462, "fuel": "Petrol", "segment": "suv"},
    # Hyundai
    {"make": "Hyundai", "model": "Creta", "variant": "SX 1.5L Turbo Petrol DCT", "cc": 1482, "fuel": "Petrol", "segment": "suv"},
    {"make": "Hyundai", "model": "Creta", "variant": "EX 1.5L Diesel", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Hyundai", "model": "Creta", "variant": "SX(O) 1.5L Diesel AT", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Hyundai", "model": "Venue", "variant": "SX 1.0L Turbo Petrol DCT", "cc": 998, "fuel": "Petrol", "segment": "suv"},
    {"make": "Hyundai", "model": "Venue", "variant": "S 1.5L Diesel", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Hyundai", "model": "i20", "variant": "Asta 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Hyundai", "model": "i20", "variant": "Sportz 1.0L Turbo DCT", "cc": 998, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Hyundai", "model": "Verna", "variant": "SX 1.5L Turbo Petrol DCT", "cc": 1482, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Hyundai", "model": "Verna", "variant": "SX(O) 1.5L Diesel AT", "cc": 1493, "fuel": "Diesel", "segment": "sedan"},
    {"make": "Hyundai", "model": "Tucson", "variant": "Signature 2.0L Diesel AT AWD", "cc": 1995, "fuel": "Diesel", "segment": "suv"},
    {"make": "Hyundai", "model": "Alcazar", "variant": "Prestige 1.5L Turbo Petrol DCT", "cc": 1482, "fuel": "Petrol", "segment": "suv"},
    {"make": "Hyundai", "model": "Exter", "variant": "SX Connect 1.2L Petrol AMT", "cc": 1197, "fuel": "Petrol", "segment": "suv"},
    {"make": "Hyundai", "model": "Grand i10 Nios", "variant": "Sportz 1.2L Petrol", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    # Tata
    {"make": "Tata", "model": "Nexon", "variant": "XZ+ 1.2L Turbo Petrol", "cc": 1199, "fuel": "Petrol", "segment": "suv"},
    {"make": "Tata", "model": "Nexon", "variant": "XZA+ 1.5L Diesel AMT", "cc": 1497, "fuel": "Diesel", "segment": "suv"},
    {"make": "Tata", "model": "Nexon EV", "variant": "Max XZ+ LR", "cc": 0, "fuel": "Electric", "segment": "suv"},
    {"make": "Tata", "model": "Punch", "variant": "Creative 1.2L Petrol AMT", "cc": 1199, "fuel": "Petrol", "segment": "suv"},
    {"make": "Tata", "model": "Harrier", "variant": "XZA+ 2.0L Diesel AT", "cc": 1956, "fuel": "Diesel", "segment": "suv"},
    {"make": "Tata", "model": "Safari", "variant": "XZA+ 2.0L Diesel AT", "cc": 1956, "fuel": "Diesel", "segment": "suv"},
    {"make": "Tata", "model": "Altroz", "variant": "XZ+ 1.2L Petrol", "cc": 1199, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Tata", "model": "Altroz", "variant": "XZ+ 1.5L Diesel", "cc": 1497, "fuel": "Diesel", "segment": "hatchback"},
    {"make": "Tata", "model": "Tiago", "variant": "XZ+ 1.2L Petrol", "cc": 1199, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Tata", "model": "Tigor", "variant": "XZ+ 1.2L Petrol", "cc": 1199, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Tata", "model": "Tigor EV", "variant": "XZ+ LR", "cc": 0, "fuel": "Electric", "segment": "sedan"},
    # Mahindra
    {"make": "Mahindra", "model": "Thar", "variant": "LX 2.0L Turbo Petrol AT", "cc": 1997, "fuel": "Petrol", "segment": "suv"},
    {"make": "Mahindra", "model": "Thar", "variant": "LX 2.2L Diesel AT", "cc": 2184, "fuel": "Diesel", "segment": "suv"},
    {"make": "Mahindra", "model": "XUV700", "variant": "AX7 L 2.0L Turbo Petrol AT", "cc": 1997, "fuel": "Petrol", "segment": "suv"},
    {"make": "Mahindra", "model": "XUV700", "variant": "AX7 L 2.2L Diesel AT AWD", "cc": 2184, "fuel": "Diesel", "segment": "suv"},
    {"make": "Mahindra", "model": "Scorpio N", "variant": "Z8 L 2.0L Turbo Petrol AT", "cc": 1997, "fuel": "Petrol", "segment": "suv"},
    {"make": "Mahindra", "model": "Scorpio N", "variant": "Z8 L 2.2L Diesel AT 4WD", "cc": 2184, "fuel": "Diesel", "segment": "suv"},
    {"make": "Mahindra", "model": "XUV400", "variant": "EL Pro", "cc": 0, "fuel": "Electric", "segment": "suv"},
    {"make": "Mahindra", "model": "XUV300", "variant": "W8(O) 1.2L Turbo Petrol", "cc": 1197, "fuel": "Petrol", "segment": "suv"},
    {"make": "Mahindra", "model": "Bolero", "variant": "B6(O) 1.5L Diesel", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Mahindra", "model": "Bolero Neo", "variant": "N10(O) 1.5L Diesel", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    # Kia
    {"make": "Kia", "model": "Seltos", "variant": "HTX+ 1.5L Turbo Petrol DCT", "cc": 1482, "fuel": "Petrol", "segment": "suv"},
    {"make": "Kia", "model": "Seltos", "variant": "GTX+ 1.5L Diesel AT", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Kia", "model": "Sonet", "variant": "HTX+ 1.0L Turbo Petrol DCT", "cc": 998, "fuel": "Petrol", "segment": "suv"},
    {"make": "Kia", "model": "Sonet", "variant": "HTX+ 1.5L Diesel AT", "cc": 1493, "fuel": "Diesel", "segment": "suv"},
    {"make": "Kia", "model": "Carens", "variant": "Prestige Plus 1.5L Turbo Petrol DCT", "cc": 1482, "fuel": "Petrol", "segment": "mpv"},
    {"make": "Kia", "model": "EV6", "variant": "GT Line AWD", "cc": 0, "fuel": "Electric", "segment": "suv"},
    # Volkswagen
    {"make": "Volkswagen", "model": "Taigun", "variant": "GT Plus 1.5L TSI DSG", "cc": 1498, "fuel": "Petrol", "segment": "suv"},
    {"make": "Volkswagen", "model": "Taigun", "variant": "Topline 1.0L TSI AT", "cc": 999, "fuel": "Petrol", "segment": "suv"},
    {"make": "Volkswagen", "model": "Virtus", "variant": "GT Plus 1.5L TSI DSG", "cc": 1498, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Volkswagen", "model": "Virtus", "variant": "Topline 1.0L TSI AT", "cc": 999, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Volkswagen", "model": "Polo", "variant": "Highline Plus 1.0L TSI", "cc": 999, "fuel": "Petrol", "segment": "hatchback"},
    # Skoda
    {"make": "Skoda", "model": "Kushaq", "variant": "Style 1.5L TSI DSG", "cc": 1498, "fuel": "Petrol", "segment": "suv"},
    {"make": "Skoda", "model": "Kushaq", "variant": "Active 1.0L TSI AT", "cc": 999, "fuel": "Petrol", "segment": "suv"},
    {"make": "Skoda", "model": "Slavia", "variant": "Style 1.5L TSI DSG", "cc": 1498, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Skoda", "model": "Slavia", "variant": "Active 1.0L TSI", "cc": 999, "fuel": "Petrol", "segment": "sedan"},
    # Toyota
    {"make": "Toyota", "model": "Fortuner", "variant": "Legender 2.8L Diesel AT 4WD", "cc": 2755, "fuel": "Diesel", "segment": "suv"},
    {"make": "Toyota", "model": "Fortuner", "variant": "4x2 2.7L Petrol AT", "cc": 2694, "fuel": "Petrol", "segment": "suv"},
    {"make": "Toyota", "model": "Innova Crysta", "variant": "ZX 2.4L Diesel AT", "cc": 2393, "fuel": "Diesel", "segment": "mpv"},
    {"make": "Toyota", "model": "Innova Hycross", "variant": "ZX(O) Hybrid CVT", "cc": 1987, "fuel": "Hybrid", "segment": "mpv"},
    {"make": "Toyota", "model": "Urban Cruiser Hyryder", "variant": "V Hybrid CVT", "cc": 1462, "fuel": "Hybrid", "segment": "suv"},
    {"make": "Toyota", "model": "Glanza", "variant": "V AMT", "cc": 1197, "fuel": "Petrol", "segment": "hatchback"},
    # Honda
    {"make": "Honda", "model": "City", "variant": "ZX 1.5L Petrol CVT", "cc": 1498, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Honda", "model": "City", "variant": "V 1.5L Diesel", "cc": 1498, "fuel": "Diesel", "segment": "sedan"},
    {"make": "Honda", "model": "City Hybrid", "variant": "ZX e:HEV", "cc": 1498, "fuel": "Hybrid", "segment": "sedan"},
    {"make": "Honda", "model": "Amaze", "variant": "VX 1.2L Petrol CVT", "cc": 1199, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Honda", "model": "Elevate", "variant": "ZX 1.5L Petrol CVT", "cc": 1498, "fuel": "Petrol", "segment": "suv"},
    # MG
    {"make": "MG", "model": "Hector", "variant": "Sharp Pro 1.5L Turbo Petrol CVT", "cc": 1451, "fuel": "Petrol", "segment": "suv"},
    {"make": "MG", "model": "Hector", "variant": "Sharp Pro 2.0L Diesel", "cc": 1956, "fuel": "Diesel", "segment": "suv"},
    {"make": "MG", "model": "Astor", "variant": "Sharp 1.5L Petrol CVT", "cc": 1498, "fuel": "Petrol", "segment": "suv"},
    {"make": "MG", "model": "ZS EV", "variant": "Exclusive Pro", "cc": 0, "fuel": "Electric", "segment": "suv"},
    {"make": "MG", "model": "Comet EV", "variant": "Playful", "cc": 0, "fuel": "Electric", "segment": "hatchback"},
    # Renault
    {"make": "Renault", "model": "Kiger", "variant": "RXZ 1.0L Turbo CVT", "cc": 999, "fuel": "Petrol", "segment": "suv"},
    {"make": "Renault", "model": "Kwid", "variant": "Climber 1.0L AMT", "cc": 999, "fuel": "Petrol", "segment": "hatchback"},
    # Nissan
    {"make": "Nissan", "model": "Magnite", "variant": "XV Premium 1.0L Turbo CVT", "cc": 999, "fuel": "Petrol", "segment": "suv"},
    # Citroen
    {"make": "Citroen", "model": "C3", "variant": "Shine 1.2L Turbo", "cc": 1199, "fuel": "Petrol", "segment": "hatchback"},
    {"make": "Citroen", "model": "C3 Aircross", "variant": "Max 1.2L Turbo AT", "cc": 1199, "fuel": "Petrol", "segment": "suv"},
    # Jeep
    {"make": "Jeep", "model": "Compass", "variant": "Model S 2.0L Diesel AT 4x4", "cc": 1956, "fuel": "Diesel", "segment": "suv"},
    {"make": "Jeep", "model": "Meridian", "variant": "Limited (O) 2.0L Diesel AT", "cc": 1956, "fuel": "Diesel", "segment": "suv"},
    # BMW
    {"make": "BMW", "model": "3 Series", "variant": "320d M Sport", "cc": 1995, "fuel": "Diesel", "segment": "sedan"},
    {"make": "BMW", "model": "X1", "variant": "sDrive20i M Sport", "cc": 1998, "fuel": "Petrol", "segment": "suv"},
    {"make": "BMW", "model": "X3", "variant": "xDrive20d M Sport", "cc": 1995, "fuel": "Diesel", "segment": "suv"},
    # Mercedes
    {"make": "Mercedes-Benz", "model": "C-Class", "variant": "C 200 AMG Line", "cc": 1496, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Mercedes-Benz", "model": "GLC", "variant": "300 4MATIC", "cc": 1999, "fuel": "Petrol", "segment": "suv"},
    {"make": "Mercedes-Benz", "model": "A-Class Limousine", "variant": "A 200d", "cc": 1950, "fuel": "Diesel", "segment": "sedan"},
    # Audi
    {"make": "Audi", "model": "A4", "variant": "Premium Plus 2.0 TFSI", "cc": 1984, "fuel": "Petrol", "segment": "sedan"},
    {"make": "Audi", "model": "Q3", "variant": "Technology 2.0 TFSI Quattro", "cc": 1984, "fuel": "Petrol", "segment": "suv"},
    {"make": "Audi", "model": "Q5", "variant": "Technology 2.0 TDI Quattro", "cc": 1968, "fuel": "Diesel", "segment": "suv"},
    # Land Rover
    {"make": "Land Rover", "model": "Defender", "variant": "110 X-Dynamic SE D300", "cc": 2996, "fuel": "Diesel", "segment": "suv"},
    # Volvo
    {"make": "Volvo", "model": "XC40", "variant": "B4 Ultimate", "cc": 1969, "fuel": "Petrol", "segment": "suv"},
    {"make": "Volvo", "model": "XC60", "variant": "B5 Ultimate", "cc": 1969, "fuel": "Petrol", "segment": "suv"},
    # Mini
    {"make": "Mini", "model": "Cooper", "variant": "S 3-Door", "cc": 1998, "fuel": "Petrol", "segment": "hatchback"},
]

assert len(CAR_DATABASE) == 100, f"Expected 100 cars, got {len(CAR_DATABASE)}"

# ── Insurers ─────────────────────────────────────────────────────────────────

INSURERS = [
    {"id": "icici_lombard", "name": "ICICI Lombard", "network_garages": 7800, "claim_settlement": 96.4, "logo": "🏦"},
    {"id": "hdfc_ergo", "name": "HDFC Ergo", "network_garages": 7200, "claim_settlement": 95.8, "logo": "🏛️"},
    {"id": "bajaj_allianz", "name": "Bajaj Allianz", "network_garages": 6500, "claim_settlement": 94.2, "logo": "🔵"},
    {"id": "oriental", "name": "Oriental Insurance", "network_garages": 7356, "claim_settlement": 87.5, "logo": "🟠"},
    {"id": "royal_sundaram", "name": "Royal Sundaram", "network_garages": 7800, "claim_settlement": 93.0, "logo": "🟡"},
    {"id": "zuno", "name": "Zuno (Edelweiss)", "network_garages": 2200, "claim_settlement": 96.0, "logo": "🟢"},
    {"id": "digit", "name": "Go Digit", "network_garages": 3700, "claim_settlement": 97.1, "logo": "💜"},
    {"id": "acko", "name": "Acko General", "network_garages": 2100, "claim_settlement": 95.5, "logo": "🔴"},
    {"id": "tata_aig", "name": "Tata AIG", "network_garages": 6800, "claim_settlement": 94.8, "logo": "🔷"},
    {"id": "new_india", "name": "New India Assurance", "network_garages": 8200, "claim_settlement": 88.0, "logo": "🇮🇳"},
    {"id": "sbi_general", "name": "SBI General", "network_garages": 5500, "claim_settlement": 91.3, "logo": "🏪"},
    {"id": "united_india", "name": "United India Insurance", "network_garages": 6100, "claim_settlement": 86.5, "logo": "🤝"},
]

# ── Add-ons ──────────────────────────────────────────────────────────────────

ADDONS = [
    {
        "id": "zero_dep",
        "name": "Zero Depreciation",
        "short_name": "Zero Dep",
        "description": "Also known as bumper-to-bumper cover, this add-on ensures you get the total amount for your car parts without any deduction for depreciation at the time of claim.",
        "popular": True,
        "mandated": False,
        "base_percent": 0.08,  # % of premium
    },
    {
        "id": "roadside_assist",
        "name": "24x7 Roadside Assistance",
        "short_name": "RSA",
        "description": "Get immediate help when your car has broken down or been in an accident with emergency services such as breakdown towing, flat tyre repair, fuel delivery, and others.",
        "popular": False,
        "mandated": False,
        "base_percent": 0.01,
    },
    {
        "id": "engine_protect",
        "name": "Engine Protect",
        "short_name": "Engine Protect",
        "description": "Covers the costs of repairing or replacing internal engine parts due to water ingression, hydrostatic lock, or leakage of coolant due to vehicle's accident.",
        "popular": False,
        "mandated": False,
        "base_percent": 0.04,
    },
    {
        "id": "pa_cover",
        "name": "Compulsory Personal Accident Cover",
        "short_name": "PA Cover",
        "description": "Compulsory Rs 15 Lakhs cover for medical expenses if the owner gets injured in an accident while driving. Covers for monetary compensation in case of hospitalization, disability or death.",
        "popular": False,
        "mandated": True,
        "base_price": 675,
    },
    {
        "id": "consumables",
        "name": "Consumables Cover",
        "short_name": "Consumables",
        "description": "Consumables like oil, nuts and bolts, etc. are not covered at the time of claims. Save on expenses on consumables which are unfit for further use due to accidental damage with this cover.",
        "popular": False,
        "mandated": False,
        "base_percent": 0.02,
    },
    {
        "id": "key_lock",
        "name": "Key and Locks Protect",
        "short_name": "Key Protect",
        "description": "Covers the cost of replacing lost, stolen, or damaged car keys.",
        "popular": False,
        "mandated": False,
        "base_price": 499,
    },
    {
        "id": "return_invoice",
        "name": "Return to Invoice",
        "short_name": "RTI",
        "description": "Get the full replacement cost of your vehicle in the event of theft or total loss. This reimburses the entire invoice value, including the ex-showroom price, road tax, registration fees, and insurance costs.",
        "popular": True,
        "mandated": False,
        "base_percent": 0.06,
    },
    {
        "id": "personal_belongings",
        "name": "Loss of Personal Belongings",
        "short_name": "Personal Belongings",
        "description": "Cover loss of personal belongings due to car theft or break-in with this add-on cover.",
        "popular": False,
        "mandated": False,
        "base_price": 500,
    },
    {
        "id": "ncb_protect",
        "name": "NCB Protect",
        "short_name": "NCB Protect",
        "description": "Protects your No Claim Bonus even if you make a claim during the policy period. Your NCB discount stays intact for the next renewal.",
        "popular": True,
        "mandated": False,
        "base_percent": 0.03,
    },
    {
        "id": "tyre_protect",
        "name": "Tyre Protect",
        "short_name": "Tyre Protect",
        "description": "Covers the cost of replacing or repairing damaged tyres and tubes due to accidental damage, cuts, bursts, or malicious acts.",
        "popular": False,
        "mandated": False,
        "base_percent": 0.02,
    },
]

# ── RTO code to state mapping ────────────────────────────────────────────────

RTO_STATE_MAP = {
    "KA": "Karnataka", "MH": "Maharashtra", "DL": "Delhi", "TN": "Tamil Nadu",
    "KL": "Kerala", "AP": "Andhra Pradesh", "TS": "Telangana", "GJ": "Gujarat",
    "RJ": "Rajasthan", "UP": "Uttar Pradesh", "WB": "West Bengal", "MP": "Madhya Pradesh",
    "HR": "Haryana", "PB": "Punjab", "CH": "Chandigarh", "GA": "Goa",
    "HP": "Himachal Pradesh", "JK": "Jammu & Kashmir", "UK": "Uttarakhand",
    "OR": "Odisha", "CG": "Chhattisgarh", "JH": "Jharkhand", "BR": "Bihar",
    "AS": "Assam",
}

# ── NCB slabs ────────────────────────────────────────────────────────────────

NCB_SLABS = {
    0: "0%", 1: "20%", 2: "25%", 3: "35%", 4: "45%", 5: "50%",
}

# ── Helper functions ─────────────────────────────────────────────────────────

def _deterministic_seed(reg_number: str) -> int:
    return int(hashlib.md5(reg_number.encode()).hexdigest(), 16)


def lookup_registration(reg_number: str) -> dict | None:
    """Map registration number to a car from the database (deterministic mock)."""
    reg_number = reg_number.upper().replace(" ", "").replace("-", "")
    # Extract state code
    state_code = reg_number[:2] if len(reg_number) >= 2 else None
    state = RTO_STATE_MAP.get(state_code, "Unknown")

    seed = _deterministic_seed(reg_number)
    car_index = seed % len(CAR_DATABASE)
    car = CAR_DATABASE[car_index].copy()

    # Deterministic registration year between 2015-2025
    reg_year = 2015 + (seed % 11)

    return {
        "registration_number": reg_number,
        "make": car["make"],
        "model": car["model"],
        "variant": car["variant"],
        "cc": car["cc"],
        "fuel_type": car["fuel"],
        "segment": car["segment"],
        "registration_year": reg_year,
        "rto_state": state,
        "full_name": f"{car['make']} {car['model']} {car['variant']} {car['cc']} CC {car['fuel']}",
    }


def _calculate_base_idv(car: dict, reg_year: int) -> int:
    """Calculate approximate IDV based on car segment, CC, and age."""
    # Base ex-showroom prices by segment
    segment_base = {
        "hatchback": 600000, "sedan": 1000000, "suv": 1200000, "mpv": 1100000,
    }
    base = segment_base.get(car["segment"], 900000)

    # Adjust for CC
    cc = car.get("cc", 1200)
    if cc == 0:  # Electric
        base *= 1.8
    elif cc > 2000:
        base *= 1.6
    elif cc > 1500:
        base *= 1.2

    # Depreciation by age
    age = 2026 - reg_year
    dep_rates = {0: 0, 1: 0.15, 2: 0.20, 3: 0.30, 4: 0.40, 5: 0.50}
    dep = dep_rates.get(age, 0.50 + min(age - 5, 5) * 0.05)
    idv = int(base * (1 - dep))
    return max(idv, 50000)


def get_quotes(car_info: dict, policy_type: str = "comprehensive", ncb_years: int = 0) -> list[dict]:
    """Generate mock insurance quotes from all insurers."""
    seed = _deterministic_seed(car_info["registration_number"])
    random.seed(seed)

    idv = _calculate_base_idv(car_info, car_info["registration_year"])
    ncb_percent = {0: 0, 1: 20, 2: 25, 3: 35, 4: 45, 5: 50}.get(ncb_years, 50)

    quotes = []
    for insurer in INSURERS:
        # Base OD premium: ~3-5% of IDV
        od_rate = random.uniform(0.028, 0.052)
        od_premium = int(idv * od_rate)

        # Third party premium based on CC
        cc = car_info.get("cc", 1200)
        if cc == 0:
            tp_premium = 2094
        elif cc <= 1000:
            tp_premium = 2094
        elif cc <= 1500:
            tp_premium = 3416
        else:
            tp_premium = 7897

        if policy_type == "comprehensive":
            ncb_discount = int(od_premium * ncb_percent / 100)
            premium = od_premium - ncb_discount + tp_premium
        else:
            premium = tp_premium
            idv = 0

        # Price variation per insurer
        variation = random.uniform(0.85, 1.15)
        premium = int(premium * variation)

        # Random features
        instant_issuance = random.random() > 0.3
        price_drop = random.random() > 0.6

        quotes.append({
            "insurer_id": insurer["id"],
            "insurer_name": insurer["name"],
            "logo": insurer["logo"],
            "idv": idv,
            "premium": premium,
            "od_premium": od_premium if policy_type == "comprehensive" else 0,
            "tp_premium": tp_premium,
            "ncb_discount": ncb_discount if policy_type == "comprehensive" else 0,
            "ncb_percent": ncb_percent,
            "network_garages": insurer["network_garages"],
            "claim_settlement": insurer["claim_settlement"],
            "instant_issuance": instant_issuance,
            "price_drop": price_drop,
            "policy_type": policy_type,
        })

    random.seed()  # Reset
    quotes.sort(key=lambda x: x["premium"])
    return quotes


def get_addon_prices(base_premium: int, car_info: dict) -> list[dict]:
    """Calculate add-on prices based on base premium."""
    seed = _deterministic_seed(car_info["registration_number"])
    random.seed(seed)

    addon_prices = []
    for addon in ADDONS:
        if "base_percent" in addon:
            price = int(base_premium * addon["base_percent"] * random.uniform(0.8, 1.3))
            price = max(price, 99)
        else:
            price = int(addon["base_price"] * random.uniform(0.8, 1.2))

        addon_prices.append({
            **addon,
            "price": price,
        })

    random.seed()
    return addon_prices
