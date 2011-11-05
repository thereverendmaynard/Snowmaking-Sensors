#!/usr/bin/env python
import serial, time, datetime, sys
from xbee import xbee
import twitter
import MySQLdb
from time import strftime

USEDATABASE = True

message = "Woa - you shouldnt see this"

#init global dbsamples
dbsample1 = 0  # variable to set frequency of db updates (dont want to thrash the server - what is appropriate?
dbsample2 = 0  # variable to set frequency of db updates (dont want to thrash the server - what is appropriate?
dbsample3 = 0  # variable to set frequency of db updates (dont want to thrash the server - what is appropriate?
dbsample4 = 0

sql = ""
db = MySQLdb.connect(host="websitename.com",user="username",passwd="password",db="dbname")

# Define the sensors and their ports

# Sensor #1
# Original Killawatt


KILLAWATT1 = 1         # XBEE ID #1
CURRENTSENSE = 4       # which XBee ADC has current draw data
VOLTSENSE = 0          # which XBee ADC has mains voltage data


# Sensor #2 - Solar Panel

SOLAR_XBEE_ID = 2
SOLAR_BATTERY_VOLTAGE = 0
SOLAR_PANEL_VOLTAGE = 1
SOLAR_TEMP = 2

# Sensor #3 - Compressor

COMP_XBEE_ID = 3      # XBEE ID # 2
PUMP_PRES = 0         # AD PIN 0 for Water Pressure
PUMP_AMPS = 1         # AD PIN 1 for Water Pump Amps
PUMP_TEMP = 2         # AD PIN 2 for Water Temp
COMP_PRES = 3         # AD PIN 3 for Air Pressure
COMP_TEMP = 4         # AD PIN 4 for Air Temp
#COMP_AMPS = 4        # AD PIN 4 for Compressor Current Usage


# TBD

# Sensor#4 - TBD - Testing

TBD_XBEE_ID = 4



# define the comm settings

if sys.platform=="linux2":
    SERIALPORT = "/dev/usb/tts/0"    # the com/serial port the XBee is connected to (this one is for linux)
else:
    SERIALPORT = "COM3"               # the com/serial port the XBee is connected to (this one is for windows)

BAUDRATE = 9600      # the baud rate we talk to the xbee

# other constants

MAINSVPP = 170 * 2     # +-170V is what 120Vrms ends up being (= 120*2sqrt(2))
vrefcalibration = [492,  # Calibration for sensor #0
                   498,  # Calibration for sensor #1
                   489,  # Calibration for sensor #2
                   492,  # Calibration for sensor #3
                   501,  # Calibration for sensor #4
                   493]  # etc... approx ((2.4v * (10Ko/14.7Ko)) / 3
CURRENTNORM = 15.5  # conversion to amperes from ADC
NUMWATTDATASAMPLES = 1800 # how many samples to watch in the plot window, 1 hr @ 2s samples

# Twitter username & password
# this is used to tweet sensor results
twitterusername = "username"
twitterpassword = "password"

def TwitterIt(u, p, message):
    api = twitter.Api(username=u, password=p)
 
    try:
        status = api.PostUpdate(message)
 #       print "%s just posted: %s" % (status.user.name, status.text)
    except UnicodeDecodeError:
 #       print "Your message could not be encoded.  Perhaps it contains non-ASCII characters? "
 #       print "Try explicitly specifying the encoding with the  it with the --encoding flag"
        potato =1
    except:
        potato =1
 # print "Couldn't connect, check network, username and password!"


def GetTemp (tempdata):
    # Function to convert a set of temp sensor readings to a temp in deg F

    tempavg = 0
    tempavgmV = 0
    tempC = 0
    tempF = 0
    
    for i in range(len(tempdata)):
        tempavg = tempavg+tempdata[i]

    tempavg /= len(tempdata)
    tempavgmV = GetVolts (tempavg)
    tempC = (tempavgmV-460)/10
    tempF = (tempC*1.8)+32

    return tempF

def GetVolts (sensorvalue):
# this is converting response to 3.3v over 1024 samples 
# the a/d converter is 8 bit - hence 1024 possible values
    return ((3300/1024)*sensorvalue)


def GetAirPres (sensorvalue):
    presavg = 0         # 0-300 PSI, Vout = 1-5v, Vin = 12v, Sensor goes to 5v, but we are never going above 120 so should not exceed 3.3v
    pressure = 0
    ratio = 0.0

    for i in range(len(sensorvalue)):
        presavg = presavg+sensorvalue[i]

    presavg /= len(sensorvalue)
    presvolts = presavg * (3300/1024)    #convert to millivolts on the 3.3v xbee
    pressure = ((300/4000.0)*presvolts)-60     
    
    if pressure <= 10:
        pressure = 1
        
    return(pressure); # subtract 150 (that appears to be 1 volt) and scale 


def GetWaterPres (sensorvalue):
    presavg = 0         # 0-1000 PSI, Vout = 1-5v, Vin 10-30V, PSI = .125X -125
    pressure = 0        # Sensor voltage go to 5v, but we will use a voltage divider to get it down to 3.4v (R1 =4.7k, R2 = 10k)
    ratio = 0.0
    for i in range(len(sensorvalue)):
        presavg = presavg+sensorvalue[i]

    presavg /= len(sensorvalue)
    presvolts = presavg * (3400/1024)    #convert to millivolts on the 3.3v xbee
    pressure = ((500/2761.0)*presvolts)-115
    if pressure <= 10:
        pressure = 1
        
    return(pressure); 

def GetSolarVoltage (sensorvalue):

    voltavg = 0
    volts = 0

    for i in range(len(sensorvalue)):
        voltavg = voltavg+sensorvalue[i]
    voltavg /= len(sensorvalue)
    volts = voltavg * (3300/1024)    #convert to millivolts on the 3.3v xbee
    volts = (volts/.162)/1000         # reverse my voltage divider circuit
        
    return(volts); # subtract 150 (that appears to be 1 volt) and scale     

# open up the FTDI serial port to get data transmitted to xbee
ser = serial.Serial(SERIALPORT, BAUDRATE)
ser.open()

samplenum = 3585 # initialize sample count so we get a twitter update right away
dbsample1 = 6 # initialize db sample count so we get a dbupdate right away
dbsample2 = 6 # initialize db sample count so we get a dbupdate right away
dbsample3 = 6 # initialize db sample count so we get a dbupdate right away
dbsample4 = 6

# the 'main loop' runs once a second or so

def update_graph(idleevent):

global avgwattdataidx, twittertimer, DEBUG, tempdata, samplenum, dbsample1, dbsample2, dbsample3, dbsample4, db #,sensorhistories
     
    # grab one packet from the xbee, or timeout
    packet = xbee.find_packet(ser)
    if not packet:
        return        # we timedout
    
    xb = xbee(packet)             # parse the packet


###################################### Sensor 1 ###########################################################
    if xb.address_16 == KILLAWATT1:

        # we'll only store n-1 samples since the first one is usually messed up
        voltagedata = [-1] * (len(xb.analog_samples) - 1)
        ampdata = [-1] * (len(xb.analog_samples ) -1)
        # grab 1 thru n of the ADC readings, referencing the ADC constants
        # and store them in nice little arrays
        for i in range(len(voltagedata)):
            voltagedata[i] = xb.analog_samples[i+1][VOLTSENSE]
            ampdata[i] = xb.analog_samples[i+1][CURRENTSENSE]

        
        # get max and min voltage and normalize the curve to '0'
        # to make the graph 'AC coupled' / signed
        min_v = 1024     # XBee ADC is 10 bits, so max value is 1023
        max_v = 0
        for i in range(len(voltagedata)):
            if (min_v > voltagedata[i]):
                min_v = voltagedata[i]
            if (max_v < voltagedata[i]):
                max_v = voltagedata[i]

        # figure out the 'average' of the max and min readings
        avgv = (max_v + min_v) / 2
        # also calculate the peak to peak measurements
        vpp =  max_v-min_v

        for i in range(len(voltagedata)):
            #remove 'dc bias', which we call the average read
            voltagedata[i] -= avgv
            # We know that the mains voltage is 120Vrms = +-170Vpp
            voltagedata[i] = (voltagedata[i] * MAINSVPP) / vpp

        # normalize current readings to amperes
        for i in range(len(ampdata)):
            # VREF is the hardcoded 'DC bias' value, its
            # about 492 but would be nice if we could somehow
            # get this data once in a while maybe using xbeeAPI
            if vrefcalibration[xb.address_16]:
                ampdata[i] -= vrefcalibration[xb.address_16]
            else:
                ampdata[i] -= vrefcalibration[0]
            # the CURRENTNORM is our normalizing constant
            # that converts the ADC reading to Amperes
            ampdata[i] /= CURRENTNORM

        # calculate instant. watts, by multiplying V*I for each sample point
        wattdata = [0] * len(voltagedata)
        for i in range(len(wattdata)):
            wattdata[i] = voltagedata[i] * ampdata[i]

        # sum up the current drawn over one 1/60hz cycle
        avgamp = 0
        # 16.6 samples per second, one cycle = ~17 samples
        # close enough for govt work :(
        for i in range(len(ampdata)):
            avgamp += abs(ampdata[i])
        avgamp /= float(len(ampdata))

        # sum up power drawn over one 1/60hz cycle
        avgwatt = 0
        # 16.6 samples per second, one cycle = ~17 samples
        for i in range(len(wattdata)):         
            avgwatt += abs(wattdata[i])
        avgwatt /= float(len(wattdata))

        # Print out our most recent measurements
        message = ""
        message = message + "Sensor #: "+str(xb.address_16)+ " (Tweetawatt) Sample # " + str(samplenum) + ". Signal RSSI is : " + str(xb.rssi)  
        message = message + " Current draw, in amperes: "+str(avgamp)
        message = message + " Watt draw, in VA: "+str(avgwatt)

        #print message

        if dbsample1 >15:
            sql = "INSERT into databasename.sensordata(xbeeid, sensorname0, sensortime, sensorvalue0, sensortype0, sensorname1, sensorvalue1, sensortype1, samplecount, sensorRSSI) VALUES ('1','Pump Amps','" 
            sql = sql + strftime("%Y-%m-%d %H:%M:%S") + "','" + str(avgamp) + "', 'Amps','Pump Watts','" + str(avgwatt) + "','Watts','" + str(samplenum) + "','" + str(xb.rssi) + "')"          
            #print sql

            if db == 0: # check if connection is there... and open it if it isnt
                db = MySQLdb.connect(host="website",user="userid",passwd="password",db="dbn")
            try:
                curs = db.cursor()          # Get a db cursor
                curs.execute(sql)           # execute the SQL
                db.commit                   # commit the changes to the DB
                
                #print "successfull query : " + sql  # debug info
                dbsample1 = 0                # reset the couter

            except StandardError, err:
                # may have lost host
                #print "- lost host trying to reopen db - retrying" + str(err)
                db = MySQLdb.connect(host="website.com",user="username",passwd="pw",db="dbn")
                curs = db.cursor()
                curs.execute(sql)
                db.commit
                dbsample1 = 0
                #print "I think it worked... " + sql
     
        dbsample1 +=1            

####################################### Sensor 2 (solar panels) #########################################################################
# Sensor 2 data
    if (xb.address_16 ==SOLAR_XBEE_ID):

        BattTempData = [-1] * (len(xb.analog_samples)- 1)
        PanelVoltData = [-1] * (len(xb.analog_samples) -1)
        BattVoltData = [-1] * (len(xb.analog_samples) -1)

        BattTempF = 0
        BattVoltage = 0
        PanelVoltage = 0

        for i in range(len(BattTempData)):
            PanelVoltData[i] = xb.analog_samples[i+1][SOLAR_PANEL_VOLTAGE]
            BattVoltData[i] = xb.analog_samples[i+1][SOLAR_BATTERY_VOLTAGE]
            BattTempData[i] = xb.analog_samples[i+1][SOLAR_TEMP]

        BattTempF = GetTemp(BattTempData)
        BattVoltage = str(round(GetSolarVoltage(BattVoltData),2))
        PanelVoltage = str(round(GetSolarVoltage(PanelVoltData),2))
              
        #print "PanelVoltData" + str(PanelVoltData)
        #print "BattVoltData" + str(BattVoltData)
        #print "BattTempData" + str(BattTempData)
        #print "BattTempF" + str(BattTempF)
        #print "BattVoltage" + str(BattVoltage)
        #print "Panelvoltage" + str(PanelVoltage)

        message = "Solar Panel Battery Voltage is " + BattVoltage + " and panel voltage is " + PanelVoltage

        if dbsample2 > 15:

            sql = "INSERT into databasename.sensordata(xbeeid, sensortime, samplecount, sensorRSSI,";
            sql = sql + "sensorname0,sensorvalue0,sensortype0,";
            sql = sql + "sensorname1,sensorvalue1,sensortype1,";
            sql = sql + "sensorname2,sensorvalue2,sensortype2) VALUES";
            sql = sql + " ('2','" + strftime("%Y-%m-%d %H:%M:%S") + "','" + str(samplenum) + "','" + str(xb.rssi) + "',";
            sql = sql + "'Batt Volt','" + BattVoltage + "','Volts',";  # pin0 - Battery Volts
            sql = sql + "'Panel Volt','" + PanelVoltage + "','Volts',";  # pin1 - Panel Volts
            sql = sql + "'Batt Temp','" + str(BattTempF) + "','Temp')";  # pin2 - Battery Temp

            if db == 0: # check if connection is there... and open it if it isnt
                db = MySQLdb.connect(host="website.com",user="userid",passwd="password",db="dbname")

            try:
                curs = db.cursor()          # Get a db cursor
                curs.execute(sql)           # execute the SQL
                db.commit                   # commit the changes to the DB
                dbsample2 = 0                # reset the couter

            except StandardError, err:
                # may have lost host
                db = MySQLdb.connect(host="website.com",user="userid",passwd="password",db="dbname")
                curs = db.cursor()
                curs.execute(sql)
                db.commit
                dbsample2 = 0

        dbsample2+=1          
##################################################################################################################################

    if (xb.address_16 == TBD_XBEE_ID):

        BattTempF = 0
        BattVoltage = 0
        PanelVoltage = 0

 
        
######################################## Sensor 3 (pumps) #######################################################################

    if (xb.address_16 == COMP_XBEE_ID):  # COMP_XBEE_ID =3

        #COMP_XBEE_ID = 3      # XBEE ID # 3
        #PUMP_PRES = 0         # AD PIN 0 for Water Pressure
        #PUMP_AMPS = 1         # AD PIN 1 for Water Pump Amps
        #PUMP_TEMP = 2         # AD PIN 2 for Water Temp
        #COMP_PRES = 3         # AD PIN 3 for Air Pressure
        #COMP_TEMP = 4         # AD PIN 4 for Air Temp

        pump_pres = [-1] * (len(xb.analog_samples) - 1)
        pump_amps = [-1] * (len(xb.analog_samples) -1)
        pump_temp = [-1] * (len(xb.analog_samples) -1)

        comp_pres = [-1] * (len(xb.analog_samples) -1)
        comp_temp = [-1] * (len(xb.analog_samples) -1)
        
        for i in range(len(comp_temp)):
            pump_pres[i] = xb.analog_samples[i+1][PUMP_PRES]
            pump_amps[i] = xb.analog_samples[i+1][PUMP_AMPS]
            pump_temp[i] = xb.analog_samples[i+1][PUMP_TEMP]

            comp_pres[i] = xb.analog_samples[i+1][COMP_PRES]
            comp_temp[i] = xb.analog_samples[i+1][COMP_TEMP]

        CompTempF = GetTemp(comp_temp)
        PumpTempF = GetTemp(pump_temp)
        PumpPresPSI = GetWaterPres(pump_pres)       # This function is for the 1000PSI Gauge
        CompPresPSI = GetAirPres(comp_pres)         # this function is for the 300PSI Gauge
        
        if dbsample3 > 2:
            
            sql = "INSERT into databasename.sensordata(xbeeid, sensortime, samplecount, sensorRSSI,";
            sql = sql + "sensorname0,sensorvalue0,sensortype0,";
            sql = sql + "sensorname1,sensorvalue1,sensortype1,";
            sql = sql + "sensorname2,sensorvalue2,sensortype2,";
            sql = sql + "sensorname3,sensorvalue3,sensortype3,";
            sql = sql + "sensorname4,sensorvalue4,sensortype4) VALUES";
            sql = sql + " ('3','" + strftime("%Y-%m-%d %H:%M:%S") + "','" + str(samplenum) + "','" + str(xb.rssi) + "',";
            sql = sql + "'Pump Pres','" + str(PumpPresPSI) + "','Pres',";  # pin0 - Water Pressure
            sql = sql + "'Pump Amps','" + "0" + "','Amps',";  # pin1 - Water Amps
            sql = sql + "'Comp Temp','" + str(CompTempF) + "','Temp',";  # pin2 - Air Temp
            sql = sql + "'Comp Pres','" + str(CompPresPSI) + "','Pres',";  # pin3 - Air Pressure
            sql = sql + "'Pump Temp','" + str(PumpTempF) + "','Temp')";  # pin4 - Water Temp

            if db == 0: # check if connection is there... and open it if it isnt
                db = MySQLdb.connect(host="website.com",user="userid",passwd="pw",db="db")

            try:
                curs = db.cursor()          # Get a db cursor
                curs.execute(sql)           # execute the SQL
                db.commit                   # commit the changes to the DB
                dbsample3 = 0                # reset the couter

            except StandardError, err:
                # may have lost host
                db = MySQLdb.connect(host="website.com",user="userid",passwd="password",db="dbname")
                curs = db.cursor()
                curs.execute(sql)
                db.commit
                dbsample2 = 0
        
        message = "Compressor Temp is : " + str(CompTempF) + " Signal RSSI is : " + str(xb.rssi)
        dbsample3 +=1

#####################################################################################################################################

    samplenum += 1

    if (samplenum/3600 == 1):

        TwitterIt(twitterusername, twitterpassword, message)
        samplenum = 0

while True:
    update_graph(None)


