from pysnmp.hlapi import *

ip = "192.168.1.12"
community = "public"

# Walk the system tree to find CPU-related OIDs
print("Walking UniFi/EdgeSwitch MIB tree (1.3.6.1.4.1.4413)...")
print("="*60)

for (errorIndication,
     errorStatus,
     errorIndex,
     varBinds) in nextCmd(SnmpEngine(),
                          CommunityData(community),
                          UdpTransportTarget((ip, 161), timeout=5.0, retries=1),
                          ContextData(),
                          ObjectType(ObjectIdentity('1.3.6.1.4.1.4413')),
                          lexicographicMode=False):

    if errorIndication:
        print(f"Error: {errorIndication}")
        break
    elif errorStatus:
        print(f'Error: {errorStatus.prettyPrint()} at {errorIndex}')
        break
    else:
        for varBind in varBinds:
            oid_str = str(varBind[0])
            value = str(varBind[1])
            # Look for anything that might be CPU or load related
            if any(keyword in oid_str.lower() or keyword in value.lower() 
                   for keyword in ['cpu', 'load', 'processor', 'util']):
                print(f"{oid_str} = {value}")
        
