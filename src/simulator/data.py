from __future__ import annotations

import pandas as pd


REFERENCE_CASES = {
    "Case-1": {
        "sample": "8#",
        "feeds": {
            "Biomass": (4000.0, 25.0, 15.0),
            "CIN": (12.2, 25.0, 15.0),
            "O2IN": (1290.6, 280.0, 15.0),
            "H2OIN": (449.3, 280.0, 15.0),
            "N2IN": (122.6, 25.0, 15.0),
            "CO2IN": (691.47, 25.0, 15.0),
            "POSTO2": (60.2, 280.0, 15.0),
            "POSTH2O": (355.23, 280.0, 15.0),
            "POSTCO2": (39.27, 250.0, 15.0),
            "O2POX": (961.6, 20.0, 15.0),
        },
        "expected": {
            "inci_top_kg_h": 6899.0,
            "inci_slag_kg_h": 122.0,
            "pox_gas_kg_h": 7787.0,
            "pox_ash_kg_h": 73.33,
            "inci_comp": {"CO": 32.47, "H2": 34.48, "CO2": 25.44, "CH4": 4.56},
            "pox_comp": {"CO": 46.23, "H2": 28.37, "CO2": 21.79, "CH4": 0.08},
            "rmsd_inci_pct": 0.84,
            "rmsd_pox_pct": 0.06,
        },
    },
    "Case-2": {
        "sample": "11#",
        "feeds": {
            "Biomass": (4000.0, 25.0, 15.0),
            "CIN": (20.3, 25.0, 15.0),
            "O2IN": (1188.8, 280.0, 15.0),
            "H2OIN": (413.9, 280.0, 15.0),
            "N2IN": (110.4, 25.0, 15.0),
            "CO2IN": (692.85, 25.0, 15.0),
            "POSTO2": (57.49, 280.0, 15.0),
            "POSTH2O": (356.89, 280.0, 15.0),
            "POSTCO2": (39.27, 250.0, 15.0),
            "O2POX": (903.1, 20.0, 15.0),
        },
        "expected": {
            "inci_top_kg_h": 6677.0,
            "inci_slag_kg_h": 262.0,
            "pox_gas_kg_h": 7458.7,
            "pox_ash_kg_h": 121.6,
            "inci_comp": {"CO": 32.18, "H2": 34.64, "CO2": 25.52, "CH4": 4.17},
            "pox_comp": {"CO": 45.61, "H2": 27.96, "CO2": 22.37, "CH4": 0.06},
            "rmsd_inci_pct": 0.94,
            "rmsd_pox_pct": 0.06,
        },
    },
    "Case-3": {
        "sample": "11#",
        "feeds": {
            "Biomass": (2400.0, 25.0, 15.0),
            "CIN": (12.2, 25.0, 15.0),
            "O2IN": (735.6, 280.0, 15.0),
            "H2OIN": (256.1, 280.0, 15.0),
            "N2IN": (72.2, 25.0, 15.0),
            "CO2IN": (415.71, 25.0, 15.0),
            "POSTO2": (60.22, 280.0, 15.0),
            "POSTH2O": (355.22, 280.0, 15.0),
            "POSTCO2": (39.27, 250.0, 15.0),
            "O2POX": (540.4, 20.0, 15.0),
        },
        "expected": {
            "inci_top_kg_h": 4225.0,
            "inci_slag_kg_h": 182.0,
            "pox_gas_kg_h": 4692.0,
            "pox_ash_kg_h": 73.0,
            "inci_comp": {"CO": 30.73, "H2": 35.50, "CO2": 26.56, "CH4": 3.68},
            "pox_comp": {"CO": 43.42, "H2": 27.88, "CO2": 24.47, "CH4": 0.05},
            "rmsd_inci_pct": 0.94,
            "rmsd_pox_pct": 0.07,
        },
    },
}


DEFAULT_REACTOR_SPECS = {
    "INCI_T_C": 900.0,
    "SLAG_T_C": 800.0,
    "RGPOX_T_C": 1400.0,
    "SYSTEM_P_BAR": 15.0,
    "INCI_HEAT_LOSS_MW": 0.1,
    "RGPOX_HEAT_LOSS_MW": 0.1,
    "INCI_C_CONV": 0.85,
    "RGPOX_C_CONV": 1.0,
    "ASH_TO_SLAG_FRAC": 0.60,
    "CHAR_TO_SLAG_FRAC": 0.55,
}


DEFAULT_CHEMISTRY_SETUP = {
    "Sample": "8#",
    "Tar Formula": "CHO0.082N0.01",
    "Tar Yield Factor": "0.01 * C_dry",
    "Tar target H/C": 1.20,
    "O2 Purity vol%": 95.0,
    "H2S/COS split to H2S": 0.80,
    "RGPOX CH4 Target @1300C (%)": 0.55,
    "RGPOX CH4 Target @1400C (%)": 0.10,
    "RGPOX CH4 Target @1500C (%)": 0.05,
    "Constraint Mode": "Restricted Equilibrium",
}


def build_feed_df(case_id: str = "Case-1") -> pd.DataFrame:
    case = REFERENCE_CASES[case_id]
    rows = []
    for stream_name, payload in case["feeds"].items():
        mass, temp_c, p_bar = payload
        rows.append(
            {
                "Stream": stream_name,
                "MassFlow_kg_h": mass,
                "Temp_C": temp_c,
                "Pressure_bar": p_bar,
            }
        )
    return pd.DataFrame(rows)


def build_specs_df() -> pd.DataFrame:
    rows = [{"Parameter": key, "Value": value} for key, value in DEFAULT_REACTOR_SPECS.items()]
    return pd.DataFrame(rows)


def build_chem_df(case_id: str = "Case-1") -> pd.DataFrame:
    config = dict(DEFAULT_CHEMISTRY_SETUP)
    config["Sample"] = REFERENCE_CASES[case_id]["sample"]
    rows = [{"Field": key, "Value": value} for key, value in config.items()]
    return pd.DataFrame(rows)
