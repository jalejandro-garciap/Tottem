# comments in English; UI strings will be provided by the caller
import usb.core
import usb.util

def _endpoint_addr(ep):
    return int(ep.bEndpointAddress)

def scan_printers():
    """Scan USB devices and return plausible ESC/POS printers with endpoints.
    Returns a list of dicts: {vid, pid, interface, eps_out, eps_in}
    """
    devices = []
    for dev in usb.core.find(find_all=True):
        info = {"vid": f"0x{dev.idVendor:04x}", "pid": f"0x{dev.idProduct:04x}"}
        try:
            cfg = dev.get_active_configuration()
        except usb.core.USBError:
            # Try default configuration 0 if inactive
            try:
                dev.set_configuration()
                cfg = dev.get_active_configuration()
            except Exception:
                cfg = None
        eps_out, eps_in = [], []
        iface_index = 0
        if cfg:
            for i, iface in enumerate(cfg):
                for ep in iface.endpoints():
                    addr = _endpoint_addr(ep)
                    # OUT if direction bit not set; IN if set
                    if addr & 0x80:
                        eps_in.append(addr)
                    else:
                        eps_out.append(addr)
                # prefer first interface with both endpoints
                if eps_out and eps_in:
                    iface_index = i
                    break
        info.update({
            "interface": iface_index,
            "eps_out": sorted(set(eps_out)),
            "eps_in": sorted(set(eps_in)),
        })
        # Heuristic: expose all devices; UI will let user pick
        devices.append(info)
    # Return only unique entries
    uniq = []
    seen = set()
    for d in devices:
        k = (d['vid'], d['pid'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(d)
    return uniq
