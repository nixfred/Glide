#!/usr/bin/env python3
"""Publish and discover only on physical private LANs while the user is active."""
import json
import re
import time
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from glide_network import CONFIG, atomic, identity, interfaces, on_lan, session_active

TYPE = '_omarchy-glide._udp'
PATH = '/'
API = 'org.freedesktop.Avahi'


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    server = dbus.Interface(bus.get_object(API, PATH), API + '.Server')
    groups, browsers, devices = [], [], {}
    signature = None
    own = None
    links = []

    def save():
        unique = {}
        for device in devices.values():
            if own and device['id'] != own['id'] and on_lan(device['ip'], links):
                unique[device['id']] = device
        atomic(CONFIG/'discovery.json', json.dumps({'updated':time.time(),'devices':list(unique.values())}))

    def found(index, protocol, name, kind, domain, flags):
        try:
            resolved = server.ResolveService(index, protocol, name, kind, domain, 0, 0)
            _, _, _, _, _, hostname, address_protocol, address, port, txt, _ = resolved
            if int(address_protocol) != 0 or int(port) != 4242 or not on_lan(str(address), links): return
            fields = {}
            for item in txt:
                value = bytes(item).decode('utf-8', errors='strict')
                if '=' in value:
                    key, value = value.split('=', 1); fields[key] = value
            if fields.get('v') != '1' or fields.get('session') != 'active': return
            fp = fields.get('fp','')
            if not re.fullmatch(r'(?:[0-9a-f]{2}:){31}[0-9a-f]{2}', fp): return
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,62}', fields.get('host','')): return
            if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', fields.get('user','')): return
            device = {'id':fp.replace(':','')[:32], 'name':fields['host'], 'user':fields['user'],
                      'fingerprint':fp, 'ip':str(address), 'active':True, 'version':1}
            devices[(int(index),str(name),str(domain))] = device
            save()
        except Exception as error:
            print('Ignored discovery response: '+str(error), flush=True)

    def removed(index, protocol, name, kind, domain, flags):
        devices.pop((int(index),str(name),str(domain)), None)
        save()

    def refresh():
        nonlocal signature, own, links
        try:
            own = identity()
            links = interfaces()
            current = (own['active'], tuple((i['index'],i['ip']) for i in links), own['fingerprint'])
            if current != signature:
                for group in groups:
                    try: group.Reset(); group.Free()
                    except dbus.DBusException: pass
                for browser in browsers:
                    try: browser.Free()
                    except dbus.DBusException: pass
                groups.clear(); browsers.clear(); devices.clear()
                signature = current
                if own['active'] and links:
                    # Advertise only the interface the sharing daemon binds to.
                    primary = links[0]
                    group = dbus.Interface(bus.get_object(API, server.EntryGroupNew()), API+'.EntryGroup')
                    txt = ['v=1','session=active','host='+own['name'],'user='+own['user'],'fp='+own['fingerprint']]
                    txt = dbus.Array([dbus.ByteArray(s.encode()) for s in txt], signature='ay')
                    group.AddService(primary['index'], 0, dbus.UInt32(0), 'Glide '+own['name']+' '+own['user'], TYPE, '', '', dbus.UInt16(4242), txt)
                    group.Commit(); groups.append(group)
                    for link in links:
                        browser = dbus.Interface(bus.get_object(API, server.ServiceBrowserNew(link['index'],0,TYPE,'',dbus.UInt32(0))), API+'.ServiceBrowser')
                        browser.connect_to_signal('ItemNew', found)
                        browser.connect_to_signal('ItemRemove', removed)
                        browsers.append(browser)
                    print('LAN discovery active on '+', '.join(i['name'] for i in links), flush=True)
                else: print('LAN discovery withdrawn: no active unlocked desktop or physical LAN', flush=True)
            save()
        except Exception as error:
            print('Discovery refresh: '+str(error), flush=True)
        return True

    refresh()
    GLib.timeout_add_seconds(5, refresh)
    GLib.MainLoop().run()

if __name__ == '__main__': main()
