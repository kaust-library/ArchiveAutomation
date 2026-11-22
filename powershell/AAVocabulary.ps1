<#
Shared vocabulary for PowerShell scripts (e.g. the physical-archives
metadata_import_*.ps1 scripts), read from ArchiveAutomation's vocabulary folder,
so digital and physical ingests use the same allowed values as Libnova.

Load it at the top of a script:

    . "C:\Tools\ArchiveAutomation\powershell\AAVocabulary.ps1"
    $enumFix = Get-AAEnumFix

$enumFix has the same shape as the hand-written tables it replaces:
    $enumFix["DC.TYPE"]["still image"]  ->  "Still Image"
It covers DC.TYPE, DC.LANGUAGE, appraised and accession. Keep the lists current
with:  archiveautomation-vocab refresh-libnova

Works in Windows PowerShell 5.1 and PowerShell 7.
#>

function Get-AAVocabularyPath {
    # vocabulary\ next to this script's folder, i.e. C:\Tools\ArchiveAutomation\vocabulary
    return (Join-Path (Split-Path -Parent $PSScriptRoot) "vocabulary")
}

function Read-AAJson([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Vocabulary file not found: $Path"
    }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-AAEnumFix {
    <#
    Returns @{ iecode = @{ lower-case value = official spelling } } for every
    controlled field in enums.json.
    #>
    param([string]$VocabularyPath = (Get-AAVocabularyPath))

    $enums = Read-AAJson (Join-Path $VocabularyPath "enums.json")
    $fix = @{}
    foreach ($field in $enums.PSObject.Properties) {
        if ($field.Name.StartsWith("_")) { continue }
        $map = @{}
        foreach ($value in $field.Value.values) {
            $map[$value.ToLower()] = $value
        }
        $fix[$field.Name] = $map
    }
    return $fix
}

function Repair-AAEnumValue {
    <#
    Splits a cell on "|" and corrects each part's spelling for a controlled
    field. Returns the corrected values as an array. Parts that are not allowed
    are returned unchanged with a warning, so they can be fixed in the CSV
    (Libnova would reject them with a 400).
    For fields that are not controlled, the parts are returned as they are.

        Repair-AAEnumValue -IECode "DC.LANGUAGE" -Value "EN | ar-sa" -EnumFix $enumFix
        ->  en, ar-SA
    #>
    param(
        [Parameter(Mandatory)][string]$IECode,
        [AllowEmptyString()][string]$Value,
        [Parameter(Mandatory)][hashtable]$EnumFix,
        [string]$Item = ""
    )

    $parts = @($Value -split "\s*\|\s*" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
    if (-not $EnumFix.ContainsKey($IECode)) { return ,$parts }

    $fixed = @()
    foreach ($part in $parts) {
        $key = $part.ToLower()
        if ($EnumFix[$IECode].ContainsKey($key)) {
            $fixed += $EnumFix[$IECode][$key]
        } else {
            $where = ""
            if ($Item) { $where = " ($Item)" }
            Write-Warning ("{0}: '{1}' is not allowed{2}. Allowed: {3}" -f
                $IECode, $part, $where, (($EnumFix[$IECode].Values | Sort-Object) -join ", "))
            $fixed += $part
        }
    }
    return ,$fixed
}

function Get-AARightsAccess {
    <#
    The DC.RIGHTS_ACCESS sentence for a level (Public, Internal, Restricted,
    Highly Restricted), from rights_access.json. Restricted names -Source.

        Get-AARightsAccess -Level "Restricted" -Source "Office of the Provost"
    #>
    param(
        [Parameter(Mandatory)][string]$Level,
        [string]$Source = "",
        [string]$VocabularyPath = (Get-AAVocabularyPath)
    )

    $levels = (Read-AAJson (Join-Path $VocabularyPath "rights_access.json")).levels
    foreach ($entry in $levels.PSObject.Properties) {
        if ($entry.Name -eq $Level.Trim()) {    # -eq ignores case
            $sentence = $entry.Value
            if ($sentence.Contains("{DC.SOURCE}")) {
                if (-not $Source) { throw "DC.RIGHTS_ACCESS ${Level} needs -Source (the approving office)." }
                $sentence = $sentence.Replace("{DC.SOURCE}", $Source)
            }
            return $sentence
        }
    }
    throw ("'{0}' is not an access level. Allowed: {1}" -f
        $Level, (($levels.PSObject.Properties | ForEach-Object { $_.Name }) -join ", "))
}
