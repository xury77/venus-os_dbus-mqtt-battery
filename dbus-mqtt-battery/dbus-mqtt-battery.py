#!/usr/bin/env python

from gi.repository import GLib
import platform
import logging
import sys
import os
import time
import json
import paho.mqtt.client as mqtt
import configparser # for config/ini file
import _thread

# import Victron Energy packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'ext', 'velib_python'))
from vedbus import VeDbusService


# get values from config.ini file
try:
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    if (config['MQTT']['broker_address'] == "IP_ADDR_OR_FQDN"):
        print("ERROR:config.ini file is using invalid default values like IP_ADDR_OR_FQDN. The driver restarts in 60 seconds.")
        time.sleep(60)
        sys.exit()
except:
    print("ERROR:config.ini file not found. Copy or rename the config.sample.ini to config.ini. The driver restarts in 60 seconds.")
    time.sleep(60)
    sys.exit()


# Get logging level from config.ini
# ERROR = shows errors only
# WARNING = shows ERROR and warnings
# INFO = shows WARNING and running functions
# DEBUG = shows INFO and data/values
if 'DEFAULT' in config and 'logging' in config['DEFAULT']:
    if config['DEFAULT']['logging'] == 'DEBUG':
        logging.basicConfig(level=logging.DEBUG)
    elif config['DEFAULT']['logging'] == 'INFO':
        logging.basicConfig(level=logging.INFO)
    elif config['DEFAULT']['logging'] == 'ERROR':
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.WARNING)


# set variables
connected = 0
last_changed = 0
last_updated = 0

#formatting
_a = lambda p,  v: (str("%.2f" % v) + 'A')
_ah = lambda p, v: (str("%.2f" % v) + 'Ah')
_n = lambda p,  v: (str("%i"   % v))
_p = lambda p,  v: (str("%.2f" % v) + '%')
_s = lambda p,  v: (str("%s"   % v))
_t = lambda p,  v: (str("%.2f" % v) + '°C')
_v = lambda p,  v: (str("%.2f" % v) + 'V')
_v3 = lambda p, v: (str("%.3f" % v) + 'V')
_w = lambda p,  v: (str("%.2f" % v) + 'W')

battery_dict = {

    # general data
    '/Dc/0/Power':                          {'value': None, 'textformat': _w},
    '/Dc/0/Voltage':                        {'value': None, 'textformat': _v},
    '/Dc/0/Current':                        {'value': None, 'textformat': _a},
    '/Dc/0/Temperature':                    {'value': None, 'textformat': _t},

    '/InstalledCapacity':                   {'value': None, 'textformat': _ah},
    '/ConsumedAmphours':                    {'value': None, 'textformat': _ah},
    '/Capacity':                            {'value': None, 'textformat': _ah},
    '/Soc':                                 {'value': None, 'textformat': _p},
    '/TimeToGo':                            {'value': None, 'textformat': _n},
    '/Balancing':                           {'value': None, 'textformat': _n},
    '/SystemSwitch':                        {'value': None, 'textformat': _n},

    # alarms
    '/Alarms/LowVoltage':                   {'value': 0,    'textformat': _n},
    '/Alarms/HighVoltage':                  {'value': 0,    'textformat': _n},
    '/Alarms/LowSoc':                       {'value': 0,    'textformat': _n},
    '/Alarms/HighChargeCurrent':            {'value': 0,    'textformat': _n},
    '/Alarms/HighDischargeCurrent':         {'value': 0,    'textformat': _n},
    '/Alarms/HighCurrent':                  {'value': 0,    'textformat': _n},
    '/Alarms/CellImbalance':                {'value': 0,    'textformat': _n},
    '/Alarms/HighChargeTemperature':        {'value': 0,    'textformat': _n},
    '/Alarms/LowChargeTemperature':         {'value': 0,    'textformat': _n},
    '/Alarms/LowCellVoltage':               {'value': 0,    'textformat': _n},
    '/Alarms/LowTemperature':               {'value': 0,    'textformat': _n},
    '/Alarms/HighTemperature':              {'value': 0,    'textformat': _n},
    '/Alarms/FuseBlown':                    {'value': 0,    'textformat': _n},

    # info
    '/Info/ChargeRequest':                  {'value': None, 'textformat': _n},
    '/Info/MaxChargeVoltage':               {'value': None, 'textformat': _v},
    '/Info/MaxChargeCurrent':               {'value': None, 'textformat': _a},
    '/Info/MaxDischargeCurrent':            {'value': None, 'textformat': _a},

    # history
    '/History/ChargeCycles':                {'value': None, 'textformat': _n},
    '/History/MinimumVoltage':              {'value': None, 'textformat': _v},
    '/History/MaximumVoltage':              {'value': None, 'textformat': _v},
    '/History/TotalAhDrawn':                {'value': None, 'textformat': _ah},

    # system
    '/System/MinVoltageCellId':             {'value': None, 'textformat': _s},
    '/System/MinCellVoltage':               {'value': None, 'textformat': _v3},
    '/System/MaxVoltageCellId':             {'value': None, 'textformat': _s},
    '/System/MaxCellVoltage':               {'value': None, 'textformat': _v3},

    '/System/MinTemperatureCellId':         {'value': None, 'textformat': _s},
    '/System/MinCellTemperature':           {'value': None, 'textformat': _t},
    '/System/MaxTemperatureCellId':         {'value': None, 'textformat': _s},
    '/System/MaxCellTemperature':           {'value': None, 'textformat': _t},
    '/System/MOSTemperature':               {'value': None, 'textformat': _t},

    '/System/NrOfModulesOnline':            {'value': 1,    'textformat': _n},
    '/System/NrOfModulesOffline':           {'value': 0,    'textformat': _n},

    '/System/NrOfModulesBlockingCharge':    {'value': 0,    'textformat': _n},
    '/System/NrOfModulesBlockingDischarge': {'value': 0,    'textformat': _n},

    # cell voltages
    '/Voltages/Sum':                        {'value': None, 'textformat': _v},
    '/Voltages/Diff':                       {'value': None, 'textformat': _v3},

    '/Voltages/Cell1':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell2':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell3':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell4':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell5':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell6':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell7':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell8':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell9':                      {'value': None, 'textformat': _v3},
    '/Voltages/Cell10':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell11':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell12':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell13':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell14':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell15':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell16':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell17':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell18':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell19':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell20':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell21':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell22':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell23':                     {'value': None, 'textformat': _v3},
    '/Voltages/Cell24':                     {'value': None, 'textformat': _v3},

    '/Balances/Cell1':                      {'value': None, 'textformat': _n},
    '/Balances/Cell2':                      {'value': None, 'textformat': _n},
    '/Balances/Cell3':                      {'value': None, 'textformat': _n},
    '/Balances/Cell4':                      {'value': None, 'textformat': _n},
    '/Balances/Cell5':                      {'value': None, 'textformat': _n},
    '/Balances/Cell6':                      {'value': None, 'textformat': _n},
    '/Balances/Cell7':                      {'value': None, 'textformat': _n},
    '/Balances/Cell8':                      {'value': None, 'textformat': _n},
    '/Balances/Cell9':                      {'value': None, 'textformat': _n},
    '/Balances/Cell10':                     {'value': None, 'textformat': _n},
    '/Balances/Cell11':                     {'value': None, 'textformat': _n},
    '/Balances/Cell12':                     {'value': None, 'textformat': _n},
    '/Balances/Cell13':                     {'value': None, 'textformat': _n},
    '/Balances/Cell14':                     {'value': None, 'textformat': _n},
    '/Balances/Cell15':                     {'value': None, 'textformat': _n},
    '/Balances/Cell16':                     {'value': None, 'textformat': _n},
    '/Balances/Cell17':                     {'value': None, 'textformat': _n},
    '/Balances/Cell18':                     {'value': None, 'textformat': _n},
    '/Balances/Cell19':                     {'value': None, 'textformat': _n},
    '/Balances/Cell20':                     {'value': None, 'textformat': _n},
    '/Balances/Cell21':                     {'value': None, 'textformat': _n},
    '/Balances/Cell22':                     {'value': None, 'textformat': _n},
    '/Balances/Cell23':                     {'value': None, 'textformat': _n},
    '/Balances/Cell24':                     {'value': None, 'textformat': _n},

    # IO
    '/Io/AllowToCharge':                    {'value': None, 'textformat': _n},
    '/Io/AllowToDischarge':                 {'value': None, 'textformat': _n},
    '/Io/AllowToBalance':                   {'value': None, 'textformat': _n},
    '/Io/ExternalRelay':                    {'value': None, 'textformat': _n},

}



# MQTT requests
def on_disconnect(client, userdata, rc):
    global connected
    logging.warning("MQTT client: Got disconnected")
    if rc != 0:
        logging.warning('MQTT client: Unexpected MQTT disconnection. Will auto-reconnect')
    else:
        logging.warning('MQTT client: rc value:' + str(rc))

    try:
        logging.warning("MQTT client: Trying to reconnect")
        client.connect(config['MQTT']['broker_address'])
        connected = 1
    except Exception as e:
        logging.error("MQTT client: Error in retrying to connect with broker: %s" % e)
        connected = 0

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        logging.info("MQTT client: Connected to MQTT broker!")
        connected = 1
        client.subscribe(config['MQTT']['topic'])
    else:
        logging.error("MQTT client: Failed to connect, return code %d\n", rc)

def on_message(client, userdata, msg):
    try:

        global \
            battery_dict, last_changed

        # get JSON from topic
        if msg.topic == config['MQTT']['topic']:
            if msg.payload != '' and msg.payload != b'':
                jsonpayload = json.loads(msg.payload)

                last_changed = int(time.time())

                if (
                    'Dc' in jsonpayload
                    and 'Soc' in jsonpayload
                    and 'Power' in jsonpayload['Dc']
                    and 'Voltage' in jsonpayload['Dc']
                ):

                    # save JSON data into battery_dict
                    for key_1, data_1 in jsonpayload.items():

                        if type(data_1) is dict:

                            for key_2, data_2 in data_1.items():

                                if key_1 == 'Dc':
                                    key = '/' + key_1 + '/0/' + key_2
                                else:
                                    key = '/' + key_1 + '/' + key_2

                                if key in battery_dict:
                                    battery_dict[key]['value'] = data_2
                                else:
                                    logging.warning("Received key \"" + str(key) + "\" with value \"" + str(data_2) + "\" is not valid")

                        else:

                            key = '/' + key_1
                            if key in battery_dict:
                                battery_dict[key]['value'] = data_1
                            else:
                                logging.warning("Received key \"" + str(key) + "\" with value \"" + str(data_1) + "\" is not valid")

                    # calculate possible values if missing
                    if 'Current' not in jsonpayload['Dc']:
                        battery_dict['/Dc/0/Current']['value'] = round( ( battery_dict['/Dc/0/Power']['value'] / battery_dict['/Dc/0/Voltage']['value'] ), 3 )

                    if (
                        'Capacity' not in jsonpayload
                        and battery_dict['/InstalledCapacity']['value'] is not None
                        and battery_dict['/ConsumedAmphours']['value'] is not None
                    ):
                        battery_dict['/Capacity']['value'] = ( battery_dict['/InstalledCapacity']['value'] - battery_dict['/ConsumedAmphours']['value'] )

                    if (
                        'TimeToGo' not in jsonpayload
                        and battery_dict['/Dc/0/Current']['value'] is not None
                        and battery_dict['/Capacity']['value'] is not None
                    ):
                        # if current is 0 display 30 days
                        battery_dict['/TimeToGo']['value'] = round( ( battery_dict['/Capacity']['value'] / battery_dict['/Dc/0/Current']['value'] * 60 * 60 ), 0 ) if battery_dict['/Dc/0/Current']['value'] != 0 else ( 60 * 60 * 24 * 30 )

                    if 'Voltages' in jsonpayload and len(jsonpayload['Voltages']) > 0:
                        if 'MinVoltageCellId' not in jsonpayload['System']:
                            battery_dict['/System/MinVoltageCellId']['value'] = min(jsonpayload['Voltages'], key=jsonpayload['Voltages'].get)

                        if 'MinCellVoltage' not in jsonpayload['System']:
                            battery_dict['/System/MinCellVoltage']['value'] = min(jsonpayload['Voltages'].values())

                        if 'MaxVoltageCellId' not in jsonpayload['System']:
                            battery_dict['/System/MaxVoltageCellId']['value'] = max(jsonpayload['Voltages'], key=jsonpayload['Voltages'].get)

                        if 'MaxCellVoltage' not in jsonpayload['System']:
                            battery_dict['/System/MaxCellVoltage']['value'] = max(jsonpayload['Voltages'].values())

                        if 'Sum' not in jsonpayload['Voltages']:
                            battery_dict['/Voltages/Sum']['value'] = sum(jsonpayload['Voltages'].values())

                        if (
                            'Diff' not in jsonpayload['Voltages']
                            and battery_dict['/System/MinCellVoltage']['value'] is not None
                            and battery_dict['/System/MaxCellVoltage']['value'] is not None
                        ):
                            battery_dict['/Voltages/Diff']['value'] = battery_dict['/System/MaxCellVoltage']['value'] - battery_dict['/System/MinCellVoltage']['value']

                else:
                    logging.warning("Received JSON doesn't contain minimum required values")
                    logging.warning("Example: {\"Dc\":{\"Power\":321.6,\"Voltage\":52.7},\"Soc\":63}")
                    logging.debug("MQTT payload: " + str(msg.payload)[1:])

            else:
                logging.warning("Received message was empty and therefore it was ignored")
                logging.debug("MQTT payload: " + str(msg.payload)[1:])

    except ValueError as e:
        logging.error("Received message is not a valid JSON. %s" % e)
        logging.debug("MQTT payload: " + str(msg.payload)[1:])

    except Exception as e:
        logging.error("Exception occurred: %s" % e)
        logging.debug("MQTT payload: " + str(msg.payload)[1:])



class DbusMqttBatteryService:
    def __init__(
        self,
        servicename,
        deviceinstance,
        paths,
        productname='MQTT Battery',
        customname='MQTT Battery',
        connection='MQTT Battery service'
    ):

        self._dbusservice = VeDbusService(servicename)
        self._paths = paths

        logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
        self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
        self._dbusservice.add_path('/Mgmt/Connection', connection)

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 0xFFFF)
        self._dbusservice.add_path('/ProductName', productname)
        self._dbusservice.add_path('/CustomName', customname)
        self._dbusservice.add_path('/FirmwareVersion', '1.0.0')
        #self._dbusservice.add_path('/HardwareVersion', '')
        self._dbusservice.add_path('/Connected', 1)

        self._dbusservice.add_path('/Latency', None)

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path, settings['value'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue
                )

        GLib.timeout_add(1000, self._update) # pause 1000ms before the next request


    def _update(self):

        global \
            battery_dict, last_changed, last_updated

        if last_changed != last_updated:

            for setting, data in battery_dict.items():
                self._dbusservice[setting] = data['value']

            logging.info("Battery SoC: {:.2f} V - {:.2f} %".format(battery_dict['/Dc/0/Power']['value'], battery_dict['/Soc']['value']))

            last_updated = last_changed

        # increment UpdateIndex - to show that new data is available
        index = self._dbusservice['/UpdateIndex'] + 1  # increment index
        if index > 255:   # maximum value of the index
            index = 0       # overflow from 255 to 0
        self._dbusservice['/UpdateIndex'] = index
        return True

    def _handlechangedvalue(self, path, value):
        logging.debug("someone else updated %s to %s" % (path, value))
        return True # accept the change



def main():
    _thread.daemon = True # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop
    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)


    # MQTT setup
    client = mqtt.Client("MqttBattery_" + str(config['MQTT']['device_instance']))
    client.on_disconnect = on_disconnect
    client.on_connect = on_connect
    client.on_message = on_message

    # check tls and use settings, if provided
    if 'tls_enabled' in config['MQTT'] and config['MQTT']['tls_enabled'] == '1':
        logging.info("MQTT client: TLS is enabled")

        if 'tls_path_to_ca' in config['MQTT'] and config['MQTT']['tls_path_to_ca'] != '':
            logging.info("MQTT client: TLS: custom ca \"%s\" used" % config['MQTT']['tls_path_to_ca'])
            client.tls_set(config['MQTT']['tls_path_to_ca'], tls_version=2)
        else:
            client.tls_set(tls_version=2)

        if 'tls_insecure' in config['MQTT'] and config['MQTT']['tls_insecure'] != '':
            logging.info("MQTT client: TLS certificate server hostname verification disabled")
            client.tls_insecure_set(True)

    # check if username and password are set
    if 'username' in config['MQTT'] and 'password' in config['MQTT'] and config['MQTT']['username'] != '' and config['MQTT']['password'] != '':
        logging.info("MQTT client: Using username \"%s\" and password to connect" % config['MQTT']['username'])
        client.username_pw_set(username=config['MQTT']['username'], password=config['MQTT']['password'])

     # connect to broker
    client.connect(
        host=config['MQTT']['broker_address'],
        port=int(config['MQTT']['broker_port'])
    )
    client.loop_start()

    # wait to receive first data, else the JSON is empty and phase setup won't work
    i = 0
    while battery_dict['/Dc/0/Power']['value'] is None:
        if i % 12 != 0 or i == 0:
            logging.info("Waiting 5 seconds for receiving first data...")
        else:
            logging.warning("Waiting since %s seconds for receiving first data..." % str(i * 5))
        time.sleep(5)
        i += 1

    paths_dbus = {
        '/UpdateIndex': {'value': 0, 'textformat': _n},
    }
    paths_dbus.update(battery_dict)


    pvac_output = DbusMqttBatteryService(
        servicename='com.victronenergy.battery.mqtt_battery_' + str(config['MQTT']['device_instance']),
        deviceinstance=int(config['MQTT']['device_instance']),
        customname=config['MQTT']['device_name'],
        paths=paths_dbus
        )

    logging.info('Connected to dbus and switching over to GLib.MainLoop() (= event based)')
    mainloop = GLib.MainLoop()
    mainloop.run()



if __name__ == "__main__":
  main()
