Attribute VB_Name = "GibbsSpike"
' Gibbs 迁移 Spike — 方案 B：n = n_p + B*z
' 修复：OrderSimplex 不得用 Long 交换 Double 目标值（~1E11 会溢出）

Option Explicit

Private Const SHEET_SETUP As String = "Setup"
Private Const SHEET_COMPARE As String = "Compare"
Private Const SHEET_NP As String = "n_particular"
Private Const SHEET_NULL As String = "Null_B"
Private Const SHEET_MU0 As String = "mu0"
Private Const SHEET_Z As String = "z_solution"

Private Const N_SPEC As Long = 8
Private Const N_Z As Long = 3
Private Const PENALTY_OBJ As Double = 1E+20

Public Sub RunGibbsSpikeCase1()
    On Error GoTo Fail
    Dim T_K As Double, P_bar As Double, Rgas As Double, P_ratio As Double
    Dim n_p(1 To N_SPEC) As Double
    Dim Bmat(1 To N_SPEC, 1 To N_Z) As Double
    Dim mu0(1 To N_SPEC) As Double
    Dim z(1 To N_Z) As Double
    Dim n_out(1 To N_SPEC) As Double
    Dim i As Long, row As Long
    Dim msg As String
    Dim goldVal As Double, relErr As Double

    Call ReadSetup(T_K, P_bar, Rgas, P_ratio)
    Call ReadVectors(n_p, Bmat, mu0)
    Call ReadZSeed(z)

    msg = OptimizeZ(z, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio)
    Call FlowsFromZ(z, n_p, Bmat, n_out)

    row = 2
    For i = 1 To N_SPEC
        With ThisWorkbook.Worksheets(SHEET_COMPARE)
            .Cells(row, 4).Value = n_out(i)
            goldVal = SafeCDbl(.Cells(row, 2).Value)
            relErr = Abs(n_out(i) - goldVal) / WorksheetFunction.Max(Abs(goldVal), 1E-12)
            .Cells(row, 6).Value = relErr
        End With
        row = row + 1
    Next i
    ThisWorkbook.Worksheets(SHEET_COMPARE).Cells(10, 4).Value = msg
    MsgBox "Gibbs Spike VBA 完成: " & msg, vbInformation
    Exit Sub
Fail:
    MsgBox "GibbsSpike 错误 " & Err.Number & ": " & Err.Description, vbCritical
End Sub

Private Function SafeCDbl(ByVal v As Variant) As Double
    If IsError(v) Or IsEmpty(v) Or Not IsNumeric(v) Then
        SafeCDbl = 0#
    Else
        SafeCDbl = CDbl(v)
    End If
End Function

Private Sub ReadSetup(ByRef T_K As Double, ByRef P_bar As Double, ByRef Rgas As Double, ByRef P_ratio As Double)
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(SHEET_SETUP)
    T_K = SafeCDbl(ws.Range("B3").Value)
    P_bar = SafeCDbl(ws.Range("B4").Value)
    Rgas = SafeCDbl(ws.Range("B5").Value)
    P_ratio = SafeCDbl(ws.Range("B6").Value)
    If T_K < 200# Or P_bar <= 0# Or Rgas <= 0# Or P_ratio <= 0# Then
        Err.Raise vbObjectError + 1, "GibbsSpike", "Setup 参数无效，请重新生成工作簿"
    End If
End Sub

Private Sub ReadZSeed(ByRef z() As Double)
    Dim ws As Worksheet
    Dim r As Long
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(SHEET_Z)
    If ws Is Nothing Then
        z(1) = 0#: z(2) = 0#: z(3) = 0#
        Exit Sub
    End If
    r = 2
    z(1) = SafeCDbl(ws.Cells(r, 2).Value)
    z(2) = SafeCDbl(ws.Cells(r + 1, 2).Value)
    z(3) = SafeCDbl(ws.Cells(r + 2, 2).Value)
    On Error GoTo 0
End Sub

Private Sub ReadVectors(ByRef n_p() As Double, ByRef Bmat() As Double, ByRef mu0() As Double)
    Dim ws As Worksheet
    Dim i As Long, k As Long, r As Long
    Set ws = ThisWorkbook.Worksheets(SHEET_NP)
    For i = 1 To N_SPEC
        n_p(i) = SafeCDbl(ws.Cells(i + 1, 2).Value)
    Next i
    Set ws = ThisWorkbook.Worksheets(SHEET_MU0)
    For i = 1 To N_SPEC
        mu0(i) = SafeCDbl(ws.Cells(i + 1, 2).Value)
    Next i
    Set ws = ThisWorkbook.Worksheets(SHEET_NULL)
    r = 2
    For i = 1 To N_SPEC
        For k = 1 To N_Z
            Bmat(i, k) = SafeCDbl(ws.Cells(r, 3).Value)
            r = r + 1
        Next k
    Next i
End Sub

Private Sub FlowsFromZ(ByRef z() As Double, ByRef n_p() As Double, ByRef Bmat() As Double, ByRef n_out() As Double)
    Dim i As Long, k As Long
    For i = 1 To N_SPEC
        n_out(i) = n_p(i)
        For k = 1 To N_Z
            n_out(i) = n_out(i) + Bmat(i, k) * z(k)
        Next k
        If n_out(i) < 1E-14 Then n_out(i) = 1E-14
    Next i
End Sub

Private Function GibbsObjective(ByRef z() As Double, ByRef n_p() As Double, ByRef Bmat() As Double, _
    ByRef mu0() As Double, ByVal T_K As Double, ByVal P_bar As Double, ByVal Rgas As Double, _
    ByVal P_ratio As Double, ByRef n_work() As Double) As Double
    Dim i As Long
    Dim nTot As Double, y As Double, mu As Double, pr As Double, term As Double

    Call FlowsFromZ(z, n_p, Bmat, n_work)
    nTot = 0#
    For i = 1 To N_SPEC
        nTot = nTot + n_work(i)
    Next i
    If nTot <= 1E-18 Then
        GibbsObjective = PENALTY_OBJ
        Exit Function
    End If
    pr = P_bar / P_ratio
    If pr < 1E-12 Then pr = 1E-12
    GibbsObjective = 0#
    For i = 1 To N_SPEC
        y = n_work(i) / nTot * pr
        If y < 1E-18 Then y = 1E-18
        mu = mu0(i) + Rgas * T_K * Log(y)
        term = n_work(i) * mu
        If Abs(term) > 1E+250 Then
            GibbsObjective = PENALTY_OBJ
            Exit Function
        End If
        GibbsObjective = GibbsObjective + term
    Next i
End Function

Private Function OptimizeZ(ByRef z() As Double, ByRef n_p() As Double, ByRef Bmat() As Double, _
    ByRef mu0() As Double, ByVal T_K As Double, ByVal P_bar As Double, ByVal Rgas As Double, _
    ByVal P_ratio As Double) As String
    Dim simplex(1 To 4, 1 To N_Z) As Double
    Dim f(1 To 4) As Double
    Dim n_work(1 To N_SPEC) As Double
    Dim alpha As Double, gamma As Double, rho As Double, sigma As Double
    Dim iter As Long, si As Long, sj As Long
    Dim centroid(1 To N_Z) As Double, xr(1 To N_Z) As Double, xe(1 To N_Z) As Double, xc(1 To N_Z) As Double
    Dim fr As Double, fe As Double, fc As Double, tol As Double

    alpha = 1#: gamma = 2#: rho = 0.5: sigma = 0.5
    tol = 1E-8
    simplex(1, 1) = z(1): simplex(1, 2) = z(2): simplex(1, 3) = z(3)
    For si = 2 To 4
        For sj = 1 To N_Z
            simplex(si, sj) = simplex(1, sj)
            If si = sj + 1 Then simplex(si, sj) = simplex(si, sj) + 0.05
        Next sj
        Call ProjectZ(simplex, si, n_p, Bmat)
    Next si
    For si = 1 To 4
        f(si) = GibbsObjectiveFromSimplex(simplex, si, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
    Next si

    For iter = 1 To 400
        Call OrderSimplex(simplex, f)
        If (f(4) - f(1)) < tol * (1# + Abs(f(1))) Then Exit For
        For sj = 1 To N_Z
            centroid(sj) = (simplex(1, sj) + simplex(2, sj) + simplex(3, sj)) / 3#
        Next sj
        For sj = 1 To N_Z
            xr(sj) = centroid(sj) + alpha * (centroid(sj) - simplex(4, sj))
        Next sj
        Call ProjectZVec(xr, n_p, Bmat)
        fr = GibbsObjective(xr, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
        If fr < f(1) And fr >= f(2) Then
            simplex(4, 1) = xr(1): simplex(4, 2) = xr(2): simplex(4, 3) = xr(3)
            f(4) = fr
        ElseIf fr < f(1) Then
            For sj = 1 To N_Z
                xe(sj) = centroid(sj) + gamma * (xr(sj) - centroid(sj))
            Next sj
            Call ProjectZVec(xe, n_p, Bmat)
            fe = GibbsObjective(xe, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
            If fe < fr Then
                simplex(4, 1) = xe(1): simplex(4, 2) = xe(2): simplex(4, 3) = xe(3)
                f(4) = fe
            Else
                simplex(4, 1) = xr(1): simplex(4, 2) = xr(2): simplex(4, 3) = xr(3)
                f(4) = fr
            End If
        Else
            For sj = 1 To N_Z
                xc(sj) = centroid(sj) + rho * (simplex(4, sj) - centroid(sj))
            Next sj
            Call ProjectZVec(xc, n_p, Bmat)
            fc = GibbsObjective(xc, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
            If fc < f(4) Then
                simplex(4, 1) = xc(1): simplex(4, 2) = xc(2): simplex(4, 3) = xc(3)
                f(4) = fc
            Else
                For si = 2 To 4
                    For sj = 1 To N_Z
                        simplex(si, sj) = simplex(1, sj) + sigma * (simplex(si, sj) - simplex(1, sj))
                    Next sj
                    Call ProjectZ(simplex, si, n_p, Bmat)
                    f(si) = GibbsObjectiveFromSimplex(simplex, si, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
                Next si
            End If
        End If
    Next iter
    z(1) = simplex(1, 1): z(2) = simplex(1, 2): z(3) = simplex(1, 3)
    OptimizeZ = "Nelder-Mead iter=" & iter & " f=" & Format(f(1), "0.000E+00")
End Function

Private Function GibbsObjectiveFromSimplex(ByRef simplex() As Double, ByVal idx As Long, _
    ByRef n_p() As Double, ByRef Bmat() As Double, ByRef mu0() As Double, _
    ByVal T_K As Double, ByVal P_bar As Double, ByVal Rgas As Double, ByVal P_ratio As Double, _
    ByRef n_work() As Double) As Double
    Dim z(1 To N_Z) As Double
    z(1) = simplex(idx, 1): z(2) = simplex(idx, 2): z(3) = simplex(idx, 3)
    GibbsObjectiveFromSimplex = GibbsObjective(z, n_p, Bmat, mu0, T_K, P_bar, Rgas, P_ratio, n_work)
End Function

Private Sub OrderSimplex(ByRef simplex() As Double, ByRef f() As Double)
    Dim i As Long, j As Long, k As Long
    Dim tf(1 To 4) As Double, ts(1 To 4, 1 To N_Z) As Double
    Dim swapF As Double

    For i = 1 To 4
        tf(i) = f(i)
        For k = 1 To N_Z
            ts(i, k) = simplex(i, k)
        Next k
    Next i
    For i = 1 To 3
        For j = i + 1 To 4
            If tf(j) < tf(i) Then
                swapF = tf(i): tf(i) = tf(j): tf(j) = swapF
                For k = 1 To N_Z
                    swapF = ts(i, k): ts(i, k) = ts(j, k): ts(j, k) = swapF
                Next k
            End If
        Next j
    Next i
    For i = 1 To 4
        f(i) = tf(i)
        For k = 1 To N_Z
            simplex(i, k) = ts(i, k)
        Next k
    Next i
End Sub

Private Sub ProjectZ(ByRef simplex() As Double, ByVal idx As Long, ByRef n_p() As Double, ByRef Bmat() As Double)
    Dim z(1 To N_Z) As Double
    z(1) = simplex(idx, 1): z(2) = simplex(idx, 2): z(3) = simplex(idx, 3)
    Call ProjectZVec(z, n_p, Bmat)
    simplex(idx, 1) = z(1): simplex(idx, 2) = z(2): simplex(idx, 3) = z(3)
End Sub

Private Sub ProjectZVec(ByRef z() As Double, ByRef n_p() As Double, ByRef Bmat() As Double)
    Dim i As Long, k As Long, n_i As Double, shift As Double, b2 As Double, iter As Long
    For iter = 1 To 12
        For i = 1 To N_SPEC
            n_i = n_p(i)
            For k = 1 To N_Z
                n_i = n_i + Bmat(i, k) * z(k)
            Next k
            If n_i < 0# Then
                b2 = Bmat(i, 1) * Bmat(i, 1) + Bmat(i, 2) * Bmat(i, 2) + Bmat(i, 3) * Bmat(i, 3)
                If b2 < 1E-30 Then b2 = 1E-30
                shift = (-n_i + 1E-14) / b2
                z(1) = z(1) + shift * Bmat(i, 1)
                z(2) = z(2) + shift * Bmat(i, 2)
                z(3) = z(3) + shift * Bmat(i, 3)
            End If
        Next i
    Next iter
End Sub
