import serial
import random
import time
import sys, traceback
import os
from google.cloud import firestore

leds = 512*8

database = os.environ.get('FIRESTORE_DB', '(default)')
collection = os.environ.get('LED_COLLECTION', 'led')
serial_port = os.environ.get('SERIAL_PORT', '/dev/ttyACM0')

db = firestore.Client(project=os.environ.get('PROJECT_ID', 'default'), database=database)

def clear():
    colorStr = []
    for i in range(leds):
        r = 0
        g = 0
        b = 0
        colorStr.append(r)
        colorStr.append(g)
        colorStr.append(b)
    return bytearray(colorStr)

def get_byte_data():
    # Reference the specific document
    doc_ref = db.collection(collection).document('data')

    # Fetch the document
    doc = doc_ref.get()

    # Check if the document exists
    if doc.exists:
        # Fetch the byte data
        byte_data = doc.get('data')
        if byte_data:
            return byte_data
        else:
            print("Field 'data' does not exist or is None.")
            return None
    else:
        print("Document does not exist.")
        return None

def main():
    ser_is_open = False
    try:
        doc_ref = db.collection(collection).document("data")
        print("Start polling LED data from Firestore")

        while True:
            color = get_byte_data()

            if not ser_is_open:
                try:
                    ser = serial.Serial(serial_port, 9600)
                    ser_is_open = True
                except serial.SerialException as e:
                    print("Could not open serial port: {}".format(e))

            if ser_is_open:
                ser.write(color)
            time.sleep(1)

    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
        color = clear()
        ser.write(color)
        time.sleep(1)
        ser.close()
        time.sleep(1)
    except Exception:
        traceback.print_exc(file=sys.stdout)

    sys.exit(0)


if __name__ == '__main__':
    main()
