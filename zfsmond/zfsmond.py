#!/usr/bin/env python

# A local script to parse output from ZFS monitoring programs and push
# it to a ZFSmon server.

import sys
import os
import subprocess
import logging
import requests
import tempfile
import socket
import time

from zfsmon.zfsmond.zpool import ZPool
from zfsmon.zfsmond.zmount import ZMount
ZFSMON_SERVER = "http://" + "169.228.147.132:4567"
HOSTNAME = socket.gethostname()
UPDATE_INTERVAL = 60

def main():
    # Open the log
    logging.basicConfig()
    ZFS_LOG = logging.getLogger("zfsmond")

    # Check if this host has been added yet
    # The line below checks if we got a 2xx HTTP status code
    print str(requests.get( ZFSMON_SERVER + "/" + HOSTNAME ).status_code)
    if (requests.get( ZFSMON_SERVER + "/" + HOSTNAME ).status_code / 100) != 2:
        hostdata = dict()
        try:
            with tempfile.TemporaryFile() as tf:
                subprocess.check_call(['uname', '-a'], stdout=tf)
                tf.flush()
                tf.seek(0)
                hostdata['hostname'] = HOSTNAME
                hostdata['hostdescription'] = tf.read()
        except subprocess.CalledProcessError as e:
            ZFS_LOG.error("uname called failed: " + str(e))
        
        r = requests.post( ZFSMON_SERVER + "/" + HOSTNAME,
                          data=hostdata )
        if r.status_code / 100 != 2:
            ZFS_LOG.error('An HTTP {0} error was encountered when creating a new host on {1}. '.format(str(r.status_code), ZFSMON_SERVER) + 
                           'The server replied with this: {0}'.format(r.text))
        else:
            ZFS_LOG.warning('Successfully added new host ' + HOSTNAME + ' on ' + ZFSMON_SERVER)
    
    # Main loop
    while(True): 
        # Poll for the updated information we want to send
        pools = get_pools()
        mounts = get_mounts()
        for mount in mounts:
            print mount.name
        # Do the updates once we're sure that this host exists
        if not post_update(pools):
            ZFS_LOG.warning("Not all pools could be updated.")
        if not post_update(mounts):
            ZFS_LOG.warning("Not all mounts could be updated.")

        time.sleep(UPDATE_INTERVAL)
            
def post_update(zfsobjs, hostname=HOSTNAME, server=ZFSMON_SERVER):
    """ POSTs the updated properties for a ZFS object to the webservice.
        zfsobjs is a list of AbstractZFS objects
        hostname is the hostname of this computer
        server is the zfs monitor server's hostname """
    ZFS_LOG = logging.getLogger("zfsmond.http")
    updated = dict()
    for obj in zfsobjs:
        # Check if this is a pool or a mount, and POST to the appropriate resource
        if isinstance(obj, ZPool):
            rescollection = "pools"
        elif isinstance(obj, ZMount):
            rescollection = "mounts"
        else: raise TypeError("Can't post a non-AbstractZFS object to the web service.")

        postreq = requests.post( server + "/" + hostname + "/" + rescollection + "/" + obj.name,
                                 data=obj.properties )
        if postreq.status_code / 100 != 2:
            ZFS_LOG.error(('An HTTP {statuscode} error was encountered when updating the {resource} ' +
                          '{hname}/{resname} on {serv}.').format( statuscode=str(postreq.status_code),
                                                                   resource=rescollection[:-1],
                                                                   hname=hostname,
                                                                   resname=obj.name,
                                                                   serv=server ))
        else:
            updated[obj.name] = postreq.status_code
    if len(updated) > 0:
        for res in updated.iterkeys():
            if updated[res] == 201:
                ZFS_LOG.info('Successfully created new pool {0}/{1} on {2}.'.format( HOSTNAME, res, ZFSMON_SERVER ))
            else:
                ZFS_LOG.info('Successfully updated {0}/{1} on {2}.'.format( HOSTNAME, res, ZFSMON_SERVER ))
        return True
    return False

def get_pools():
    """ Gets the active ZFS pools by calling `zpool list` and parsing the output. Returns a list of ZPool objects
        populated with the properties returned by zpool list -H -o all. """
    try:
        with tempfile.TemporaryFile() as tf:
                # Call `zpool list` with -H to not pretty-print the output (no header)
                subprocess.check_call(['zpool', 'list', '-H', '-o', 'all'], stdout=tf)
                tf.flush()
                tf.seek(0)
                poolinfostr = tf.read()
    except subprocess.CalledProcessError as e:
        log = logging.getLogger("zfsmond")
        log.error("The call to `zpool list` failed. Info: " + str(e))
        return []
    poolinfo = poolinfostr.splitlines()
    poolobjs = []
    for poolstr in poolinfo:
        poolobjs.append(ZPool(poolstr))
    return poolobjs

def get_mounts():
    """ Gets the active ZFS mounted filesystems by calling `zfs list` and parsing the output. """
    try:
        with tempfile.TemporaryFile() as tf:
                # Call `zfs list` with -H to suppress pretty-print and header row
                subprocess.check_call(['zfs', 'list', '-H', '-o', 'all'], stdout=tf)
                tf.flush()
                tf.seek(0)
                mountinfostr = tf.read()
    except subprocess.CalledProcessError as e:
        log = logging.getLogger("zfsmond")
        log.error("The call to `zfs list` failed. Info: " + str(e))
        return []
    mountinfo = mountinfostr.splitlines()
    mountobjs = []
    for mountstr in mountinfo:
        mountobjs.append(ZMount(mountstr))
    return mountobjs

if __name__ == "__main__":
    main()
