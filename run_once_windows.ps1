param(
  [string]$ConfigPath = "$PSScriptRoot\config.yaml"
)

$ErrorActionPreference = "Stop"
python "$PSScriptRoot\szu_board_sync.py" --config $ConfigPath
