Attribute VB_Name = "ModelInternals"
' 自动生成：scripts/build_simulator_workbook.py
' 内部模型常数 — 勿放入 Model_Input / Model_Output 前端表。
' Python 侧同源：config/model_parameters.json

' ===== MODEL_FIXED =====
Public Const inci_c_conversion As Double = 0.9

' ===== REACTOR_INTERNALS =====
Public Const INCI_HEAT_LOSS_MW As Double = 0.1
Public Const RGPOX_HEAT_LOSS_MW As Double = 0.1
Public Const RGPOX_C_CONV As Double = 1.0
Public Const ASH_TO_SLAG_FRAC As Double = 0.6
Public Const CHAR_TO_SLAG_FRAC As Double = 0.55

' ===== CHEMISTRY_INTERNALS =====
Public Const Tar_Formula As String = "CHO0.082N0.01"
Public Const Constraint_Mode As String = "Restricted Equilibrium"

' ===== PHYSICAL_CONSTANTS =====
Public Const atomic_weight_C As Double = 12.011
Public Const atomic_weight_H As Double = 1.008
Public Const atomic_weight_O As Double = 15.999
Public Const atomic_weight_N As Double = 14.007
Public Const atomic_weight_S As Double = 32.06
Public Const atomic_weight_Ar As Double = 39.948
Public Const molecular_weight_CO As Double = 28.01
Public Const molecular_weight_H2 As Double = 2.016
Public Const molecular_weight_CO2 As Double = 44.009
Public Const molecular_weight_CH4 As Double = 16.043
Public Const molecular_weight_H2O As Double = 18.015
Public Const molecular_weight_O2 As Double = 31.998
Public Const molecular_weight_N2 As Double = 28.014
Public Const molecular_weight_Ar As Double = 39.948
Public Const molecular_weight_H2S As Double = 34.081
Public Const molecular_weight_COS As Double = 60.075
Public Const molecular_weight_NH3 As Double = 17.031
Public Const celsius_to_kelvin_offset As Double = 273.15

' ===== GIBBS_SOLVER =====
Public Const multistart_ch4_shift_frac As Double = 0.7
Public Const multistart_ch4_to_co2_frac As Double = 0.4
Public Const multistart_ch4_to_h2_frac As Double = 0.3
Public Const multistart_co_shift_frac As Double = 0.5
Public Const flow_floor As Double = 1e-14
Public Const mole_fraction_floor As Double = 1e-18
Public Const slsqp_maxiter As Double = 800
Public Const slsqp_ftol As Double = 1e-10
Public Const balance_residual_tol As Double = 1e-05
Public Const lsq_fallback_residual_tol As Double = 1e-06

