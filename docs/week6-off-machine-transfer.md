# Recommended off-machine backup and recovery

The user requested a recommendation after the local observation completed.
Use an existing external USB drive, NTFS, protected with BitLocker To Go, with
at least **20 GiB free**. Keep its recovery key separately from the drive.
The workstation reports Windows Education and has the BitLocker inspection
command available; Education supports BitLocker enablement according to
[Microsoft](https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/).
To Go protects removable data drives; see the
[Microsoft FAQ](https://learn.microsoft.com/en-us/windows/security/information-protection/bitlocker/bitlocker-key-management-faq).
The 20 GiB free-space threshold is our transfer headroom recommendation, not the
actual bundle size or a Microsoft requirement. The bundle is about 8.35 GiB.

Use a separate x86-64 Windows computer for the initial rehearsal, with
**16 GiB RAM and 50 GiB free disk space recommended**, Python 3.12 or newer and
compatible Docker Desktop using Linux containers and the containerd image store.
These are our conservative targets based on the measured source-workstation
memory pressure and stored images/restored volumes. Docker's Windows baseline
includes 8 GiB system RAM and WSL requirements; see the
[official installation requirements](https://docs.docker.com/desktop/setup/install/windows-install/).
The packaged rehearsal needs at least 4 GiB of available Docker memory and about
25 GiB additional disk headroom. It verifies captured services/data in isolated
scratch resources; it does not test normal inference or run Langfuse.

No USB backup device, destination path or second computer/access has been provided.
All currently attached disks are internal NVMe. The recommendation selects a
procedure, not a physical destination. No transfer, drive formatting/encryption,
software installation or separate-machine rehearsal has occurred.

## Prepared transfer

The helper and receiving verifier are outside the unchanged frozen bundle:

- `test_output/week6-transfer-prep-20261013-01/Transfer-Bundle.ps1`
- `test_output/week6-transfer-prep-20261013-01/Verify-Bundle.py`

The helper defaults to **Plan** and prints the bundle size/count without copying.
With a destination it verifies a direct USB path, existing NTFS filesystem,
at least 20 GiB free, unlocked fully completed BitLocker encryption and active
protection. It refuses an existing destination and link/mount-point parents.
Copy verifies the source manifest and every source file, creates a new directory
with permissions for the current user/SYSTEM/administrators before copying private
content, copies the whole bundle using native PowerShell operations, then verifies
the complete receiving inventory and checksums. It never deletes or overwrites an
existing backup; a failed partial receiving copy remains protected for diagnosis.

After attaching and unlocking the chosen drive, use its actual path. The path
below is an example, **not a detected drive**. BitLocker/storage inspection may
require an administrator terminal:

```powershell
$backupDestination = 'F:\ScholarLens\recovery-20261012-01'
& ./test_output/week6-transfer-prep-20261013-01/Transfer-Bundle.ps1 -Action Plan -Destination $backupDestination
& ./test_output/week6-transfer-prep-20261013-01/Transfer-Bundle.ps1 -Action Copy -Destination $backupDestination
```

The prepared helper only handles this recommended encrypted USB route. A private
network destination requires its actual share path and protection/access details;
do not substitute an internal drive as an off-machine copy.

## Receiving machine

Copy the read-only `Verify-Bundle.py` separately, outside the receiving bundle;
adding it inside would alter the frozen bundle inventory. From the second
computer's terminal, using actual paths:

```powershell
python Verify-Bundle.py 'F:\ScholarLens\recovery-20261012-01'
docker image load --input 'F:\ScholarLens\recovery-20261012-01\images.tar.gz'
python -B 'F:\ScholarLens\recovery-20261012-01\recovery-tools\recovery_rehearsal.py' 'F:\ScholarLens\recovery-20261012-01' 'C:\ScholarLensRecovery\evidence-01'
```

`evidence-01` must be new. Follow the bundle's existing `RECOVERY.md`; collect
the verification/rehearsal reports and check the captured paper, vector, alias
and model fingerprints. A source-machine Docker rerun does not satisfy this
different-machine check. The frozen bundle captures the earlier verified API;
the subsequently activated caching/monitoring source/image are not in it.
Keep the local known-good copy and its protected credentials intact.

## Preparation checks

PowerShell syntax and no-copy Plan passed. An internal-drive Copy was rejected
before creating its destination. A tiny local fixture verified the actual
restricted directory ACL. Binary receiving verification passed; changed manifest,
changed file, unexpected inventory and path escape were rejected. No actual USB
copy or external encryption check was exercised because no device was supplied.
The already verified source manifest is pinned to
`a17b2ac49f8f44b74a5090510668e5c93d1fadd7afdd547b4090f350d1fb7685`.
Evidence: `test_output/week6-transfer-prep-20261013-01/`.

Preparation changed only ignored helper/fixture files and documentation. All 142
source/config/key/evaluation baseline fingerprints still match. The existing
API/cache and all original resources, frozen bundle and earlier changes remain
intact. No deployment or selector tuning.
