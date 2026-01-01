import asyncio
from pysnmp.hlapi.asyncio import *
import logging

# Define candidate OIDs for CPU/Load
CANDIDATES = [
    ("Host Resources (Core 1)", "1.3.6.1.2.1.25.3.3.1.2.1"),
    ("Host Resources (Core 196608)", "1.3.6.1.2.1.25.3.3.1.2.196608"), # Common index
    ("UCD-SNMP Load 1m", "1.3.6.1.4.1.2021.10.1.3.1"),
    ("UCD-SNMP Load 1m (Int)", "1.3.6.1.4.1.2021.10.1.5.1"),
    ("Ubiquiti EdgeSwitch 5s", "1.3.6.1.4.1.4413.1.1.1.1.4.6.1.3.1"),
    ("Ubiquiti EdgeSwitch Load", "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.1.0"),
    ("UniFi Old Load", "1.3.6.1.4.1.10002.1.1.1.4.2.1.3.1"), # Some AirMax/UniFi
]

HOST = "192.168.1.13"
COMMUNITY = "public" # Default, might need to fetch from DB if different

async def check_oids():
    print(f"Checking {HOST} for CPU metrics...")
    engine = SnmpEngine()
    
    for name, oid in CANDIDATES:
        try:
            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                engine,
                CommunityData(COMMUNITY),
                UdpTransportTarget((HOST, 161), timeout=2.0),
                ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            
            if errorIndication:
                print(f"[-] {name}: Timeout/Error ({errorIndication})")
            elif errorStatus:
                print(f"[-] {name}: SNMP Error ({errorStatus.prettyPrint()})")
            else:
                for varBind in varBinds:
                    print(f"[+] {name}: RESPONSE -> {varBind[1].prettyPrint()}")
                    
        except Exception as e:
            print(f"[-] {name}: Exception {e}")

if __name__ == "__main__":
    asyncio.run(check_oids())
