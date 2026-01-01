from pysnmp.hlapi import *

ip = "192.168.1.12"
community = "public"

# Test OIDs
oids = {
    "CPU (Alt OID)": "1.3.6.1.4.1.4413.1.1.1.1.4.6.1.3.1",
    "CPU (Standard with index 1)": "1.3.6.1.2.1.25.3.3.1.2.1",
    "Temperature": "1.3.6.1.4.1.4413.1.1.43.1.8.1.5.1.0"
}

for name, oid in oids.items():
    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(SnmpEngine(),
                   CommunityData(community),
                   UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                   ContextData(),
                   ObjectType(ObjectIdentity(oid)))
        )
        
        if errorIndication:
            print(f"{name}: ERROR - {errorIndication}")
        elif errorStatus:
            print(f"{name}: ERROR - {errorStatus.prettyPrint()}")
        else:
            for varBind in varBinds:
                print(f"{name}: {varBind[1]}")
    except Exception as e:
        print(f"{name}: EXCEPTION - {e}")
