param(
    [ValidateSet('Prepare','Server','Complete')][string]$Mode='Server',
    [string]$ServerRoot='C:\Projects\AI Server',
    [string]$RequestFile=(Join-Path $PSScriptRoot '../data/ai-enrollment/request.json'),
    [string]$ReplyFile=(Join-Path $PSScriptRoot '../data/ai-enrollment/reply.json'),
    [string]$ExpectedRequestSha,
    [string]$Endpoint,
    [string]$CaFile,
    [string]$PrivateRoot
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Security
function Read-JsonFile([string]$Path,[int]$Limit=65536) {
    if ((Get-Item -LiteralPath $Path).Length -gt $Limit) { throw 'JSON input exceeds bounds' }
    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
}
function Write-AtomicJson([string]$Path,$Value,[string]$StageDirectory) {
    $absolute=[IO.Path]::GetFullPath($Path);[IO.Directory]::CreateDirectory((Split-Path -Parent $absolute)) | Out-Null
    if(-not $StageDirectory){$StageDirectory=Split-Path -Parent $absolute}
    if([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($StageDirectory)) -ne [IO.Path]::GetPathRoot($absolute)){throw 'Atomic replacement requires existing protected staging on the same volume'}
    $temporary=Join-Path $StageDirectory ('pending-'+[guid]::NewGuid().ToString('N')+'.tmp')
    try {
        [IO.File]::WriteAllText($temporary,($Value | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
        if(Test-Path -LiteralPath $absolute){[IO.File]::Replace($temporary,$absolute,$null)}else{[IO.File]::Move($temporary,$absolute)}
    }
    finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
}
function Rsa-Values($Rsa,[bool]$Private) {
    $parameters=$Rsa.ExportParameters($Private);$result=[ordered]@{}
    $names=if($Private){@('Modulus','Exponent','D','P','Q','DP','DQ','InverseQ')}else{@('Modulus','Exponent')}
    foreach($name in $names){$result[$name]=[Convert]::ToBase64String($parameters.$name)}
    return $result
}
function Open-Rsa($Values) {
    $parameters=[Security.Cryptography.RSAParameters]::new()
    foreach($name in @('Modulus','Exponent','D','P','Q','DP','DQ','InverseQ')) {
        if($Values.$name){$parameters.$name=[Convert]::FromBase64String([string]$Values.$name)}
    }
    $rsa=[Security.Cryptography.RSACng]::new();$rsa.ImportParameters($parameters);return $rsa
}
function Bytes-Hash([byte[]]$Bytes) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Cert-Hash([string]$Pem) {
    $base64=$Pem.Replace('-----BEGIN CERTIFICATE-----','').Replace('-----END CERTIFICATE-----','') -replace '\s',''
    $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::new([Convert]::FromBase64String($base64))
    try{return (Bytes-Hash $certificate.RawData)}finally{$certificate.Dispose()}
}
function Client-Root {
    $folder=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'SampleArranger/ai'))
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    if((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Client storage is redirected'}
    return $folder
}
function Assert-Idle($Status) {
    if($Status.pause_requested -or $Status.recovery_required -or $Status.queue.accepting -ne $true -or $Status.queue.occupied -ne 0 -or $Status.queue.running -or $Status.queue.reserved -or @($Status.queue.waiting).Count -gt 0){throw 'Broker must be healthy accepting and completely idle; no active work or quarantine is overridden'}
}
if($MyInvocation.InvocationName -eq '.'){return} # Allow a bounded local crypto round-trip check.
$phase='validation'
try {
    if($Mode -eq 'Prepare') {
        if($env:COMPUTERNAME -ine 'ALIENWARE-BR'){throw 'Prepare runs on the authorized client'}
        $url=[uri]$Endpoint
        if($url.Scheme -ne 'https' -or $url.UserInfo -or $url.AbsolutePath -ne '/' -or $url.Query -or $url.Fragment){throw 'Verified broker HTTPS endpoint required'}
        $folder=Client-Root;$statePath=Join-Path $folder 'enrollment-state.json'
        if(Test-Path -LiteralPath $statePath){throw 'Existing enrollment preserved; complete it or review before preparing another'}
        $id=[guid]::NewGuid().ToString('D');$rsa=[Security.Cryptography.RSACng]::new(3072)
        try {
            $public=Rsa-Values $rsa $false
            # Only the public request enters the shared folder. Private key stays protected here.
            $privateJson=(Rsa-Values $rsa $true | ConvertTo-Json -Compress)
            $entropy=[Text.Encoding]::UTF8.GetBytes($id)
            $protected=[Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($privateJson),$entropy,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        } finally { $rsa.Dispose() }
        $privatePath=Join-Path $folder ('enrollment-'+$id+'.dpapi');[IO.File]::WriteAllBytes($privatePath,$protected)
        $caPath=Join-Path $folder ('broker-ca-'+$id+'.crt');Copy-Item -LiteralPath $CaFile -Destination $caPath
        $caHash=Cert-Hash ([IO.File]::ReadAllText($caPath))
        $request=[ordered]@{schema=1;request_id=$id;public_key=$public;endpoint=$Endpoint;ca_certificate_sha256=$caHash}
        Write-AtomicJson $RequestFile $request
        Write-AtomicJson $statePath @{schema=1;request_id=$id;private_key_file=$privatePath;endpoint=$Endpoint;ca_file=$caPath;ca_certificate_sha256=$caHash}
        $requestHash=(Get-FileHash -LiteralPath $RequestFile -Algorithm SHA256).Hash.ToLowerInvariant()
        @{prepared=$true;request_file=[IO.Path]::GetFullPath($RequestFile);request_sha256=$requestHash;private_key='current-user DPAPI; never exported'} | ConvertTo-Json
        return
    }
    if($Mode -eq 'Server') {
        if($env:COMPUTERNAME -ine 'iBuyPower2022'){throw 'Server enrollment must run on Trifecta/iBuyPower2022, not a backup or client'}
        if($ExpectedRequestSha -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $RequestFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedRequestSha){throw 'Public enrollment request differs from the owner-approved hash'}
        $request=Read-JsonFile $RequestFile;$null=[guid]::Parse($request.request_id)
        if($request.schema -ne 1 -or [Convert]::FromBase64String($request.public_key.Modulus).Length -ne 384 -or $request.public_key.Exponent -ne 'AQAB'){throw 'Expected a3072-bit public-only RSA request'}
        if(@($request.public_key.PSObject.Properties.Name | Where-Object {$_ -notin @('Modulus','Exponent')}).Count){throw 'Request contains non-public key fields'}
        $url=[uri]$request.endpoint
        if($url.Scheme -ne 'https' -or $url.UserInfo -or $url.AbsolutePath -ne '/' -or $url.Query -or $url.Fragment){throw 'Invalid broker endpoint'}
        $root=(Resolve-Path -LiteralPath $ServerRoot).Path
        $config=Read-JsonFile (Join-Path $root 'config/broker.json')
        $store=[IO.Path]::GetFullPath((Join-Path (Join-Path $root 'config') $config.credentials_file))
        if(-not $store.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Credential store is outside the verified server project'}
        $python=(Read-JsonFile (Join-Path $root 'evidence/server-python.json')).executable
        if(-not(Test-Path -LiteralPath $python)){throw 'Existing managed Python is required; nothing will be installed'}
        $admin=Join-Path $root 'scripts/broker_admin.py';$recover=Join-Path $root 'scripts/Recover-TrifectaBroker.ps1';$control=Join-Path $root 'scripts/Control-TrifectaBroker.ps1'
        $statusRaw=& $python -B $admin status;if($LASTEXITCODE -ne 0){throw 'Existing broker status failed'}
        $status=$statusRaw | ConvertFrom-Json;Assert-Idle $status
        $ca=Invoke-RestMethod 'http://127.0.0.1:2019/pki/ca/local' -TimeoutSec 5
        if((Cert-Hash $ca.root_certificate) -ne $request.ca_certificate_sha256){throw 'Live server CA differs from the existing trusted client CA; do not bypass trust'}
        if(-not $PrivateRoot) {
            $record=Join-Path $root 'evidence/broker/remote-enrollment-operation.json'
            if(Test-Path -LiteralPath $record){$prior=Read-JsonFile $record;if($prior.client_credentials_file){$PrivateRoot=Split-Path -Parent (Split-Path -Parent $prior.client_credentials_file)}}
            if(-not $PrivateRoot){$PrivateRoot=Join-Path $env:LOCALAPPDATA 'TrifectaBrokerPrivate'}
        }
        $PrivateRoot=(Resolve-Path -LiteralPath $PrivateRoot).Path
        if($PrivateRoot.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase) -or (Get-Item -LiteralPath $PrivateRoot).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Existing protected storage outside source is required'}
        $acl=Get-Acl -LiteralPath $PrivateRoot;$me=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        if(-not $acl.AreAccessRulesProtected){throw 'Existing private storage protection must be verified; no ACL is changed'}
        foreach($rule in $acl.Access){if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @($me,'S-1-5-18','S-1-5-32-544')){throw 'Unexpected access to existing private storage'}}
        $private=Join-Path $PrivateRoot 'sample-arranger-enrollment';[IO.Directory]::CreateDirectory($private) | Out-Null
        $phase='credential enrollment';$original=[IO.File]::ReadAllBytes($store);$entries=@(Read-JsonFile $store 1048576)
        $existingApps=@($entries | Where-Object {$_.principal -eq 'sample-arranger'})
        if($existingApps.Count -gt 1 -or ($existingApps.Count -eq 1 -and ($existingApps[0].role -ne 'inference' -or $existingApps[0].token.Length -lt 32))){throw 'Existing app identity requires review'}
        $before=@{};foreach($name in @('config/broker.json','config/server.json','web/Caddyfile')){$before[$name]=(Get-FileHash -LiteralPath (Join-Path $root $name)).Hash}
        if($existingApps.Count -eq 0) {
            $random=New-Object byte[] 32;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($random);$rng.Dispose()
            $entry=[pscustomobject]@{principal='sample-arranger';role='inference';token=[Convert]::ToBase64String($random).TrimEnd('=').Replace('+','-').Replace('/','_')}
            & $control -Action Drain -WaitSeconds 5 | Out-Null;if($LASTEXITCODE -ne 0){throw 'Idle drain failed'}
            if((Bytes-Hash ([IO.File]::ReadAllBytes($store))) -ne (Bytes-Hash $original)){throw 'Credential store changed during admission; preserve other enrollment work'}
            [IO.File]::WriteAllBytes((Join-Path $private ('credentials-before-'+$request.request_id+'.json')),$original)
            # Plaintext staging stays in existing protected storage. Replace preserves
            # the existing credential file metadata/ACL; no permission is weakened.
            Write-AtomicJson $store @($entries+$entry) $private
            $phase='managed idle reload';$log=Join-Path $private ('reload-'+$request.request_id+'.log')
            & $recover *> $log
            if($LASTEXITCODE -ne 0){throw 'Managed reload failed; keep the existing private log and do not bypass quarantine'}
        } else {$entry=$existingApps[0]}
        foreach($name in $before.Keys){if((Get-FileHash -LiteralPath (Join-Path $root $name)).Hash -ne $before[$name]){throw 'Model/provider/network configuration changed unexpectedly'}}
        $phase='dedicated authenticated TLS verification'
        $caPath=Join-Path $private 'public-broker-ca.crt';[IO.File]::WriteAllText($caPath,$ca.root_certificate,[Text.UTF8Encoding]::new($false))
        $verify=@'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from broker_client import BrokerClient
entries=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
entry=next(e for e in entries if e['principal']=='sample-arranger' and e['role']=='inference')
status=BrokerClient(sys.argv[3],entry['token'],ca_file=sys.argv[4]).request('GET','/api/v1/ai/status',timeout=5)
assert status['queue']['accepting'] and not status['recovery_required']
print('Dedicated application TLS status verified; no inference submitted.')
'@
        & $python -B -c $verify $root $store $request.endpoint $caPath
        if($LASTEXITCODE -ne 0){throw 'Dedicated app TLS verification failed'}
        $phase='sealed reply';$rsa=Open-Rsa $request.public_key
        try {
            $payload=@{request_id=$request.request_id;principal='sample-arranger';token=$entry.token} | ConvertTo-Json -Compress
            $sealed=$rsa.Encrypt([Text.Encoding]::UTF8.GetBytes($payload),[Security.Cryptography.RSAEncryptionPadding]::OaepSHA256)
        }finally{$rsa.Dispose()}
        Write-AtomicJson $ReplyFile @{schema=1;request_id=$request.request_id;endpoint=$request.endpoint;ca_certificate_sha256=$request.ca_certificate_sha256;algorithm='RSA-OAEP-SHA256';encrypted_token=[Convert]::ToBase64String($sealed)}
        @{enrolled=$true;principal='sample-arranger';role='inference';reply_file=[IO.Path]::GetFullPath($ReplyFile);credential='sealed to Alienware; never printed';inference_submitted=$false} | ConvertTo-Json
        return
    }
    if($Mode -eq 'Complete') {
        if($env:COMPUTERNAME -ine 'ALIENWARE-BR'){throw 'Complete runs only on the prepared client'}
        $folder=Client-Root;$state=Read-JsonFile (Join-Path $folder 'enrollment-state.json');$reply=Read-JsonFile $ReplyFile
        if($reply.schema -ne 1 -or $reply.algorithm -ne 'RSA-OAEP-SHA256' -or $reply.request_id -ne $state.request_id -or $reply.endpoint -ne $state.endpoint -or $reply.ca_certificate_sha256 -ne $state.ca_certificate_sha256){throw 'Sealed reply does not match the prepared trusted request'}
        if((Cert-Hash ([IO.File]::ReadAllText($state.ca_file))) -ne $state.ca_certificate_sha256){throw 'Prepared trusted CA changed'}
        $keyBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($state.private_key_file),[Text.Encoding]::UTF8.GetBytes($state.request_id),[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $values=[Text.Encoding]::UTF8.GetString($keyBytes) | ConvertFrom-Json;$rsa=Open-Rsa $values
        try{$plain=$rsa.Decrypt([Convert]::FromBase64String($reply.encrypted_token),[Security.Cryptography.RSAEncryptionPadding]::OaepSHA256)}finally{$rsa.Dispose()}
        $payload=[Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
        if($payload.request_id -ne $state.request_id -or $payload.principal -ne 'sample-arranger' -or $payload.token.Length -lt 32){throw 'Invalid sealed app credential'}
        $name='credential-'+[guid]::NewGuid().ToString('D')+'.dpapi'
        $protected=[Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::ASCII.GetBytes($payload.token),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        [IO.File]::WriteAllBytes((Join-Path $folder $name),$protected)
        Write-AtomicJson (Join-Path $folder 'connection.json') @{schema=1;principal='sample-arranger';endpoint=$state.endpoint;ca_file=$state.ca_file;credential_file=$name}
        Write-Output 'App connection configured under Windows current-user protection. Verify one app request; no secret was printed.'
    }
} catch {
    # Never echo parsed credential values or nested errors into Dot/chat/transcripts.
    throw ('Sample Arranger enrollment stopped at '+$phase+' ('+$_.Exception.GetType().Name+'). Preserve private logs; do not bypass guards.')
}
