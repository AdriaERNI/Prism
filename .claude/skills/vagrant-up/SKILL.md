---
name: vagrant-up
description: Start the project's Vagrant Windows Server 2022 VM (libvirt/KVM + WinRM) properly, including provisioning of IRIS and build tools, and verify it is ready to accept commands. Use when the user asks to start, boot, bring up, provision, or "get the VM running", or before any build/test work that needs the VM.
---

# vagrant-up — start the Vagrant Windows VM

This project's VM is a **Windows Server 2022** box (`jborean93/WindowsServer2022`)
managed by **Vagrant with the libvirt/KVM provider** and reached over **WinRM**
(not SSH). It runs an InterSystems IRIS Community instance plus the build toolchain
(Python 3.12, uv, PyInstaller, Inno Setup). It is used both to build the Windows
`prism.exe`/installer and to run integration tests against the packaged build.

## The one rule that breaks everything if ignored

**Every `vagrant ...` command MUST run from the `vagrant/` directory** (the directory
containing the `Vagrantfile`). Vagrant locates the machine, its state, and the
provider config from the cwd. Run from the repo root and it will either fail or
operate on the wrong/no machine.

```bash
cd vagrant   # then run vagrant up / status / winrm / etc. here
```

## Starting the VM

```bash
cd vagrant
vagrant up --provider=libvirt
```

This is idempotent: if the VM is already running it just reattaches and exits 0.
If it is shutoff it boots; if it does not exist it is created and **all
provisioners run in order**:

| Order | Provisioner    | What it does                                                                 |
|-------|----------------|------------------------------------------------------------------------------|
| 1     | `dns`          | Sets 8.8.8.8/8.8.4.4 on up adapters; waits for DNS resolution                |
| 2     | `tools`        | Installs Chocolatey, Python 3.12, Inno Setup, `uv`                           |
| 3     | (file)         | Uploads the IRIS installer to `C:\Users\vagrant\IRIS_installer.exe`          |
| 4     | `iris`         | Silent-installs IRIS Community to `C:\InterSystems\IRIS`                     |
| 5     | `httpd-fix`    | Adds `Listen 52773` to `httpd-local.conf` if missing                         |
| 6     | `verify`       | Opens firewall, starts IRIS services, waits for port 52773, pings REST API |

The first `vagrant up` on a fresh box takes a long time (IRIS silent install +
Chocolatey packages). WinRM timeout is 1800s. Subsequent starts of an already-
provisioned VM are fast — provisioners only re-run if changed or if you pass
`--provision`.

### Common flags

```bash
vagrant up --provider=libvirt --provision          # force all provisioners to re-run
vagrant up --provider=libvirt --no-provision       # boot only, skip provisioning
vagrant up --provider=libvirt --provision-with=tools,verify   # re-run only named ones
```

## Checking it is actually ready

`vagrant up` returning 0 means the VM booted, not that IRIS is serving. Verify
before relying on it:

```bash
cd vagrant

# 1. Machine state — expect "running (libvirt)"
vagrant status

# 2. IRIS web server listening inside the guest (guest port 52773)
vagrant winrm --shell powershell --command \
  "(Test-NetConnection -ComputerName 127.0.0.1 -Port 52773).TcpTestSucceeded"

# 3. IRIS REST API responds on the forwarded host port 52774
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Basic $(printf '_SYSTEM:SYS' | base64)" \
  http://localhost:52774/api/atelier/v8/USER
```

If step 3 returns `200`/`401`-ish the server is up; `000` means IRIS is not
listening yet — see **Troubleshooting** below.

## Connection / access details

| Thing                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| Communicator         | WinRM over SSL, peer verification off                        |
| Username / password  | `vagrant` / `vagrant`                                        |
| Hostname (guest)     | `prism-win`                                                  |
| IRIS REST (host)     | `http://localhost:52774/api/atelier/v8/USER` (guest 52773)   |
| IRIS SuperServer     | `localhost:1973` (guest 1972)                                 |
| IRIS credentials     | `_SYSTEM` / `SYS`                                            |
| Shared folder         | `/vagrant` is **disabled**. Use `vagrant upload` to move files. |

## Prerequisites on the host

```bash
for cmd in vagrant virsh curl; do command -v "$cmd" >/dev/null || echo "missing: $cmd"; done
vagrant plugin list | grep -q vagrant-libvirt || vagrant plugin install vagrant-libvirt
```

`virsh` comes from `libvirt`/`libvirt-client`. The box must be present:
`vagrant box list` should show `jborean93/WindowsServer2022 (libvirt, ...)`.

## Common operations

```bash
cd vagrant
vagrant status                 # not_running / running / shutoff
vagrant halt                   # graceful shutdown
vagrant reload                 # reboot (use --provision to re-provision too)
vagrant suspend / vagrant resume
vagrant destroy                # WARNING: deletes the VM + its state; re-provisions next up
```

## Troubleshooting

- **`vagrant up` from repo root fails / "no usable default provider"** — you're
  not in `vagrant/`. `cd vagrant` and retry.
- **`fog][WARNING] Unrecognized arguments: libvirt_ip_command`** — harmless noise
  from the libvirt plugin; ignore it.
- **IRIS web server did not start (provisioner `verify` fails)** — re-run just
  the verify provisioner to get fresh logs:
  ```bash
  vagrant up --provider=libvirt --provision-with=verify
  ```
  Then inspect the IRIS httpd error logs:
  ```bash
  vagrant winrm --shell powershell --command \
    "Get-ChildItem 'C:\InterSystems\IRIS\httpd\logs' | ForEach-Object { Write-Host '---'; Get-Content \$_.FullName -Tail 20 }"
  ```
  Common cause: `httpd-fix` didn't run or the `IRIShttpd` service is stopped.
- **WinRM connection refused after boot** — Windows is still booting. Re-run
  `vagrant up` (idempotent) or wait ~30s and retry.
- **DNS provisioner fails** — the guest can't reach 8.8.8.8; check the host's
  libvirt network (`virsh net-list`, `virsh net-dhcp-leases default`).
- **Box missing** — `vagrant box add jborean93/WindowsServer2022 --provider=libvirt`.

## Related skills and scripts

- [[vagrant-run]] — run commands inside this VM once it's up.
- `vagrant/build-windows.sh` — host-side wrapper that boots the VM and builds the exe/installer.
- `vagrant/run-integration-tests.sh` — host-side wrapper that runs the integration suite in the VM.