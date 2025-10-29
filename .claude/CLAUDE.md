# Claude Code Instructions for Meshtastic Serial Bridge

## Project Context

This is the Meshtastic Serial-to-TCP Bridge - a socat-based Docker application that bridges USB-connected Meshtastic devices to TCP for MeshMonitor and other TCP-compatible applications.

## Development Workflow

### CRITICAL: Pull Request Workflow

**⚠️ NEVER push directly to `main` branch!**

All changes MUST go through pull requests:

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/description
   ```

2. **Make your changes and commit:**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

3. **Push branch and create PR:**
   ```bash
   git push -u origin feature/description
   gh pr create --title "Title" --body "Description"
   ```

4. **Wait for review and CI checks to pass**

5. **Merge via GitHub UI** (not command line)

6. **After merge, return to main:**
   ```bash
   git checkout main
   git pull
   ```

### Branch Protection

The `main` branch is protected with:
- Required pull request reviews
- Required status checks (CI/CD)
- No force pushes
- No direct commits

## Key Architecture

### Solution: socat-based Bridge

This project uses **socat** (a mature serial bridging tool) instead of custom code for maximum reliability.

### Key Files

- **`src/Dockerfile`** - Alpine + socat + python3 + avahi
- **`src/entrypoint.sh`** - Startup script (HUPCL management + mDNS + socat)
- **`docker-compose.yml`** - Service definition
- **`README.md`** - User documentation

### Critical Technical Details

#### Serial Configuration
- **HUPCL Management:** Disabled via Python's `termios` module to prevent device reboots on disconnect
- **Baud Rate:** 115200 (default, configurable)
- **Device:** `/dev/ttyUSB0` (default, configurable)

#### TCP Protocol
- **Port:** 4403 (default, configurable)
- **Binding:** `0.0.0.0` (allows remote connections)
- **Frame Format:** `[0x94][0xC3][LENGTH_MSB][LENGTH_LSB][PROTOBUF]`

#### mDNS Discovery
- **Service Type:** `_meshtastic._tcp`
- **Implementation:** Avahi service file in `/etc/avahi/services/`
- **Auto-cleanup:** Service removed on container stop
- **Requires:** Host's `/etc/avahi/services` mounted as volume

#### Docker Requirements
- **Device passthrough:** `--device=/dev/ttyUSB0:/dev/ttyUSB0`
- **Network mode:** `host` (for localhost TCP and mDNS)
- **Avahi volume:** `/etc/avahi/services:/etc/avahi/services` (for mDNS)
- **Restart policy:** `unless-stopped`

## Development Priorities

1. **Simplicity:** Keep the socat-based approach simple and maintainable
2. **Reliability:** Connection stability over features
3. **Zero Dependencies:** No Python packages required (uses only built-in `termios`)
4. **Documentation:** Keep README updated with all changes

## Testing Workflow

### Local Testing
```bash
# Build image
docker build -t meshtastic-serial-bridge -f src/Dockerfile src/

# Start bridge
docker compose up -d

# Test with meshtastic CLI
meshtastic --host localhost --info

# View logs
docker compose logs -f

# Test mDNS discovery
avahi-browse -rt _meshtastic._tcp
```

### Testing Changes
Before creating a PR:
1. Rebuild the Docker image
2. Test basic connectivity with `meshtastic --host localhost --info`
3. Verify mDNS discovery with `avahi-browse`
4. Check logs for errors
5. Verify HUPCL is disabled (no device reboots on disconnect)

## Container Size

Target: ~47MB Alpine-based image

Current dependencies:
- `socat` - Serial to TCP bridging
- `python3` - Only for HUPCL management (built-in termios module)
- `avahi` - mDNS autodiscovery

## Common Tasks

### Adding a New Feature
1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Test locally
4. Commit changes
5. Push and create PR
6. Wait for review

### Updating Documentation
1. Create branch: `git checkout -b docs/update-readme`
2. Update README.md
3. Commit and create PR
4. Merge after review

### Fixing a Bug
1. Create branch: `git checkout -b fix/bug-description`
2. Fix the issue
3. Test thoroughly
4. Commit and create PR with fix description
5. Reference any related issues

## Troubleshooting

### Device Reboots on Disconnect
- Check that HUPCL is being disabled (see startup logs)
- Verify Python3 is installed in container
- Check that `/dev/ttyUSB0` permissions are correct

### mDNS Not Working
- Verify `/etc/avahi/services` is mounted
- Check that avahi daemon is running on host
- Test with `avahi-browse -rt _meshtastic._tcp`

### Connection Issues
- Verify device exists: `ls -l /dev/ttyUSB0`
- Check baud rate matches device settings
- Test direct connection: `screen /dev/ttyUSB0 115200`
- Review container logs: `docker compose logs`

### Port Already in Use
- Stop existing bridge: `docker compose down`
- Check for other services: `ss -tnlp | grep 4403`

## What NOT to Do

- ❌ Push directly to `main` branch
- ❌ Add Python package dependencies (keep it dependency-free)
- ❌ Replace socat with custom Python code
- ❌ Skip testing before creating PR
- ❌ Commit Python cache files (`__pycache__`, `.pytest_cache`)

## What TO Do

- ✅ Always use feature branches
- ✅ Create PRs for all changes
- ✅ Test locally before pushing
- ✅ Keep the solution simple and socat-based
- ✅ Update README when adding features
- ✅ Use meaningful commit messages
- ✅ Reference issues in PRs when applicable
