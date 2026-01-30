import serial
from time import sleep, time
import pandas as pd
import os
import sys

running = True

fileName = 'TrainingYPR_[SUBJECTNAME]_[TRIAL].xlsx'
collectionDuration = 5 #collects data for 30 seconds per section test

dataCOM = serial.Serial('COM8', baudrate=115200)


sleep(1) #allow COM to connect

def readSerial():
    dataline = dataCOM.readline().decode('utf-8').strip() #get serial data and split unecessary characters in format [roll/pitch/yaw]
    splitline = dataline.split("/")
    values = list(map(float, splitline))
    roll, pitch, yaw, ax, ay, az, gx, gy, gz = values
    #print(roll, pitch, yaw)
    return roll, pitch, yaw, ax, ay, az, gx, gy, gz

    #print(roll_data)
    #print(pitch_data)
    #print(yaw_data)

# def calibrate_ref():
#     roll_data = []
#     pitch_data = []
#     #yaw_data = []
#     variance = 3
#     live_settle = 0
#     baseline_settle = 10
#     loop_count = 0
#     bar_stages = ['-', '--', '---', '----', '-----', '----', '---', '--', '-']
#     bar_index = 0
#     fwd_or_rev = 1

#     while live_settle < baseline_settle:
#         roll, pitch, ax, ay, az, gx, gy, gz = readSerial()
#         roll_data.append(roll)
#         pitch_data.append(pitch)
#         #yaw_data.append(yaw)
#         if loop_count !=0:
#             if (abs(roll_data[-1] - roll_data[-2]) <= variance and 
#                  abs(pitch_data[-1] - pitch_data[-2]) <= variance):
#                    live_settle +=1
#             else: 
#                   live_settle = 0
#         sys.stdout.write(f"\r Calibrating {bar_stages[bar_index]}  Settling Count: {live_settle}/{baseline_settle}")
#         sys.stdout.flush()
#         if fwd_or_rev == 1:
#               bar_index += 1
#               if bar_index == 9:
#                     fwd_or_rev = 0
#         if fwd_or_rev == 0:
#               bar_index -= 1
#               if bar_index == -1:
#                     fwd_or_rev = 1
#                     bar_index += 1
              


#         sleep(0.5)

        



          
        
        
      

sections = [
    "right front", "left front", "middle front", 
            "upper right base", "upper left base", "upper middle base",
            "lower right base", "lower left base", "lower middle base",
            ]

def dataCollect(section_name, duration):

    roll_data = []
    pitch_data = []
    yaw_data = []
    ax_data = []
    ay_data = []
    az_data = []
    gx_data = []
    gy_data = []
    gz_data = []
    timestamps = []

    for i in range(5, 0, -1):
             print('Collection will start in: ', i)
             sleep(1)

    print("starting collection")   
    startTime = time()
    while time() - startTime < duration:
        roll, pitch, yaw, ax, ay, az, gx, gy, gz = readSerial()
        roll_data.append(roll)
        pitch_data.append(pitch)
        yaw_data.append(yaw)
        ax_data.append(ax)
        ay_data.append(ay)
        az_data.append(az)
        gx_data.append(gx)
        gy_data.append(gy)
        gz_data.append(gz)
        timestamps.append(time()-startTime)
        print(time()-startTime)

    print("Section: ", section_name, " Data Collected")
    return {
        'Section': [section_name] *len(roll_data),
        "TimeStamp" : timestamps,
        "Roll" : roll_data,
        "Pitch" : pitch_data,
        "Yaw" : yaw_data,
        "Ax" : ax_data,
        "Ay" : ay_data,
        "Az" : az_data,
        "Gx" : gx_data,
        "Gy" : gy_data,
        "Gz" : gz_data
        }

if not os.path.exists(fileName):
       df = pd.DataFrame({
              'Section': [],
              'TimeStamp' : [],
              'Roll': [],
              'Pitch': [],
              'Yaw': [],
              'Ax' : [],
              'Ay' : [],
              'Az' : [],
              'Gx' : [],
              'Gy' : [],
              'Gz' : [] 
       })
       with pd.ExcelWriter(fileName, engine='openpyxl') as writer: #create data sheet in excel file
            df.to_excel(writer, sheet_name='YPR_Data', index=False)
            #print(f"{fileName} created with an initial sheet.")
       

while running:
   # calibrate_ref()

    print("Select a section:")
    for i, section in enumerate(sections, 1): 
                print(f"{i}: {section}")
    section_choice = int(input("Enter the number corresponding to the section: "))
    current_section = sections[section_choice - 1]

    data = dataCollect(current_section,collectionDuration)
    df = pd.DataFrame(data)

    if os.path.exists(fileName): 
        existing_df = pd.read_excel(fileName, sheet_name='YPR_Data')
        df = pd.concat([existing_df, df], ignore_index=True)

    with pd.ExcelWriter(fileName, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name='YPR_Data', index=False)
            #print(f"Data saved to {fileName}") 

    stop_input = input("Press Q to stop or Enter to continue: ")
    if stop_input.lower() == 'q':
        running = False

dataCOM.close()

    




    