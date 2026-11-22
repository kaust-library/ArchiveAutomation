# Checks powershell\AAVocabulary.ps1 against vocabulary\. Run from the
# ArchiveAutomation folder:  powershell -ExecutionPolicy Bypass -File tests\test_vocabulary.ps1
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\powershell\AAVocabulary.ps1")
$failed = 0
function Check($name, $ok) {
    if ($ok) { Write-Host "ok    $name" } else { Write-Host "FAIL  $name" -ForegroundColor Red; $script:failed++ }
}

$enumFix = Get-AAEnumFix
$enums = Get-Content (Join-Path $PSScriptRoot "..\vocabulary\enums.json") -Raw -Encoding UTF8 | ConvertFrom-Json

Check "four controlled fields" (@("DC.TYPE","DC.LANGUAGE","appraised","accession" | Where-Object { $enumFix.ContainsKey($_) }).Count -eq 4)
Check "every enums.json value is in the table" (@($enums."accession".values | Where-Object { $enumFix["accession"][$_.ToLower()] -ne $_ }).Count -eq 0)

# The lookups the existing metadata_import scripts make:
$iecode = "DC.TYPE"; $v = "physical object"
Check "TKS-style lookup DC.TYPE" ($enumFix.ContainsKey($iecode) -and $enumFix[$iecode].ContainsKey($v.ToLower()) -and $enumFix[$iecode][$v.ToLower()] -ceq "Physical Object")
Check "appraised yes -> Yes" ($enumFix["appraised"]["yes"] -ceq "Yes")
Check "accession kaust committee record" ($enumFix["accession"]["kaust committee record"] -ceq "KAUST Committee record")

# Repair-AAEnumValue: split first, then fix each part
$r = Repair-AAEnumValue -IECode "DC.LANGUAGE" -Value "EN | ar-sa" -EnumFix $enumFix
Check "language pair fixed" (($r -join ",") -ceq "en,ar-SA")
$r = Repair-AAEnumValue -IECode "DC.TYPE" -Value "text | still image" -EnumFix $enumFix
Check "two types fixed" (($r -join ",") -ceq "Text,Still Image")
$r = Repair-AAEnumValue -IECode "DC.TYPE" -Value "Text" -EnumFix $enumFix
Check "single value stays an array" ($r -is [array] -and $r.Count -eq 1 -and $r[0] -ceq "Text")
$r = Repair-AAEnumValue -IECode "subject" -Value "A | B" -EnumFix $enumFix
Check "uncontrolled field split only" (($r -join ",") -ceq "A,B")
$r = Repair-AAEnumValue -IECode "DC.TYPE" -Value "Photo" -EnumFix $enumFix -WarningVariable w -WarningAction SilentlyContinue
Check "unknown value kept, with warning" ($r[0] -ceq "Photo" -and "$w" -like "*'Photo' is not allowed*")
$r = Repair-AAEnumValue -IECode "DC.TYPE" -Value "" -EnumFix $enumFix
Check "empty cell -> no values" ($r.Count -eq 0)

# Access sentences
Check "Public sentence" ((Get-AARightsAccess -Level "public") -ceq "Public access permitted.")
Check "Restricted names the source" ((Get-AARightsAccess -Level "Restricted" -Source "Office X") -ceq "Restricted. Approval from Office X is required to access item.")
$threw = $false; try { Get-AARightsAccess -Level "Secret" | Out-Null } catch { $threw = $_.Exception.Message -like "*not an access level*" }
Check "unknown level refused" $threw

if ($failed) { Write-Host "$failed failed" -ForegroundColor Red; exit 1 } else { Write-Host "All passed"; exit 0 }
