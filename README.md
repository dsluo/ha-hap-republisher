# HomeKit Accessory Republisher

A Home Assistant custom integration that makes HomeKit accessories with broken mDNS discoverable,
for example on another VLAN behind an mDNS proxy.

## The problem

Some HomeKit accessories (seen on a Hunter SIMPLEconnect fan with an Ayla/Realtek Wi-Fi module,
firmware 1.10.41) have a minimal mDNS responder that:

- never announces its `_hap._tcp` service over multicast,
- ignores standard (QM) multicast queries,
- only answers QU ("reply to me directly") queries and legacy unicast queries (from a non-5353
  port), replying by unicast.

On a flat network this mostly works, because controllers send a QU query when they start
browsing. Behind an mDNS reflector or proxy it doesn't:

- The UniFi gateway mDNS proxy (Avahi's reflector) strips the QU bit and does not relay unicast answers.
- OPNsense's mdns-repeater and similar repeaters drop the unicast answer.
- Home Assistant's zeroconf only sends QU on its first query, so even on the same VLAN it loses
  track of the accessory (for example when its HAP port changes after a power cycle).

## What this does

For each configured accessory, every 30 seconds (configurable), the integration:

1. Sends the accessory a legacy unicast `_hap._tcp` PTR query (the one kind it answers).
2. Registers the answer (name, port, TXT, address) on Home Assistant's own zeroconf instance
   and re-announces it by multicast.

The HomeKit Device (`homekit_controller`) integration then discovers and tracks the accessory
normally, and mDNS proxies relay the announcement to other VLANs. If the accessory stops
answering, the last record stays advertised.

## Install

HACS: add this repository as a custom repository (category: Integration), install, and restart
Home Assistant.

Manual: copy `custom_components/hap_republisher` into your `config/custom_components/` and restart.

Then go to **Settings > Devices & services > Add integration > HomeKit Accessory Republisher** and
enter the accessory's IP address. Give the accessory a fixed IP (DHCP reservation).

## Requirements

- Home Assistant must be able to reach the accessory on UDP 5353 (the query) and on its HAP TCP
  port (control). Routed access across VLANs is fine.
- The accessory's IP should not change.
