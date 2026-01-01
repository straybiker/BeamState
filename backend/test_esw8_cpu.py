from pysnmp.hlapi import *

ip = "192.168.1.12"
community = "public"

# Test various CPU-related OIDs for UniFi Switch 8 (ESW-8)
# Based on UniFi Switch MIB and common patterns

test_oids = [
    # UniFi Switch specific OIDs
    ("CPU Load (5sec)", "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.1.0"),
    ("CPU Load (1min)", "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.2.0"),
    ("CPU Load (5min)", "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.3.0"),
    
    # Try the temperature branch nearby
    ("Nearby temp OID +1", "1.3.6.1.4.1.4413.1.1.43.1.8.1.5.2.0"),
    ("Nearby temp OID +2", "1.3.6.1.4.1.4413.1.1.43.1.8.1.5.3.0"),
    
    # Try common CPU stats OIDs
    ("System Stats CPU", "1.3.6.1.4.1.4413.1.1.43.1.15.1.1.0"),
    ("System Stats CPU Alt", "1.3.6.1.4.1.4413.1.1.43.1.15.1.2.0"),
]

print(f"Testing CPU OIDs for ESW-8 at {ip}")
print("="*70)

for name, oid in test_oids:
    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(SnmpEngine(),
                   CommunityData(community),
                   UdpTransportTarget((ip, 161), timeout=2.0, retries=1),
                   ContextData(),
                   ObjectType(ObjectIdentity(oid)))
        )
        
        if errorIndication:
            print(f"{name:30} | OID: {oid:50} | ERROR: {errorIndication}")
        elif errorStatus:
            print(f"{name:30} | OID: {oid:50} | ERROR: {errorStatus.prettyPrint()}")
        else:
            for varBind in varBinds:
                value = str(varBind[1])
                if value and value != "":
                    print(f"{name:30} | OID: {oid:50} | ✓ VALUE: {value}")
                else:
                    print(f"{name:30} | OID: {oid:50} | Empty")
    except Exception as e:
        print(f"{name:30} | OID: {oid:50} | EXCEPTION: {e}")

print("="*70)
