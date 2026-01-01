from pysnmp.hlapi import *

ip = "192.168.1.14"
community = "public"

# Test various OIDs for UniFi AP
test_oids = [
    # Standard system OIDs
    ("System Description", "1.3.6.1.2.1.1.1.0"),
    ("System Name", "1.3.6.1.2.1.1.5.0"),
    ("System Uptime", "1.3.6.1.2.1.1.3.0"),
    
    # UniFi AP specific OIDs (different branch than switches)
    ("UAP Temperature", "1.3.6.1.4.1.41112.1.6.1.2.1.5.1.0"),
    ("UAP CPU Usage", "1.3.6.1.4.1.41112.1.6.1.2.1.4.1.0"),
    ("UAP Memory Usage", "1.3.6.1.4.1.41112.1.6.1.2.1.3.1.0"),
    
    # Try standard HOST-RESOURCES MIB
    ("HR Storage RAM", "1.3.6.1.2.1.25.2.3.1.6.1"),
    ("HR CPU Load", "1.3.6.1.2.1.25.3.3.1.2.768"),
    
    # Try the switch OIDs to confirm they don't work
    ("Switch Temp OID", "1.3.6.1.4.1.4413.1.1.43.1.8.1.5.1.0"),
    ("Switch CPU OID", "1.3.6.1.4.1.4413.1.1.43.1.8.1.4.1.0"),
]

print(f"Testing SNMP OIDs for UniFi AP at {ip}")
print("="*80)

for name, oid in test_oids:
    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(SnmpEngine(),
                   CommunityData(community),
                   UdpTransportTarget((ip, 161), timeout=3.0, retries=1),
                   ContextData(),
                   ObjectType(ObjectIdentity(oid)))
        )
        
        if errorIndication:
            print(f"{name:30} | {oid:45} | ERROR: {errorIndication}")
        elif errorStatus:
            print(f"{name:30} | {oid:45} | ERROR: {errorStatus.prettyPrint()}")
        else:
            for varBind in varBinds:
                value = str(varBind[1])
                if value and value != "":
                    print(f"{name:30} | {oid:45} | ✓ VALUE: {value}")
                else:
                    print(f"{name:30} | {oid:45} | Empty")
    except Exception as e:
        print(f"{name:30} | {oid:45} | EXCEPTION: {e}")

print("="*80)
