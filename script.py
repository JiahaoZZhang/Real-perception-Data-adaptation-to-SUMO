import os
import sys
import math
import pandas as pd
import sumolib
import traci
import numpy as np
from datetime import datetime, timedelta
import argparse

# Add SUMO tools path
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))



if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", type=str,
                        help="input trace file")
    args = parser.parse_args()

    try:
        df = pd.read_csv(args.file, delimiter=',', encoding='utf-8')

        gp = df.groupby("SUMO TIME")
        time_keys = np.array(list(gp.groups.keys()))
        # print(time_keys)

        sumoBinary = sumolib.checkBinary('sumo')
        traci.start([
            sumoBinary,
            "-c", "symaps.sumo.cfg", "--no-step-log", '--no-warnings',
            # "-n", "symaps.net.xml", "--no-step-log", '--no-warnings',
            # "--summary-output", "summary2.xml",
            # "--summary-output.period", "60",
            "--num-clients", "2"
        ]
        ,port=5243
        )
        traci.setOrder(4) 
        net =  sumolib.net.readNet("./symaps.net.xml")
        
        lasttimestamp = 0
        injected_vehicles = set([])
        injected_persons = set([])

        for timestamp, group in gp:

            current_vehicles = list(traci.vehicle.getIDList())
            current_persons = list(traci.person.getIDList())

            perceived_vehicles = []
            perceived_persons = []
            for _, row in group.iterrows():
                object_id = str(row['Id'])
                x = float(row['X'])
                y = float(row['Y'])
                speed = float(row['Speed'])
                object_class = str(row['Class'])
                edge = str(row['edge'])
                depart = str(row['departure'])
                destination = str(row['destination'])

                # print(object_id,x,y,object_class,edge)
                if object_class == "VEHICLE":
                    perceived_vehicles.append(object_id)
                    if object_id not in injected_vehicles:
                        r_id = f"{object_id}_{timestamp}"
                        traci.route.add(r_id,[edge])
                        traci.vehicle.add(vehID=object_id, routeID=r_id)
                        traci.vehicle.moveToXY(vehID=object_id, edgeID=edge, laneIndex=-1,
                                            x=x, y=y, keepRoute=0)
                        traci.vehicle.setSpeed(vehID=object_id, speed=speed)
                    else:
                        traci.vehicle.moveToXY(vehID=object_id, edgeID=edge, laneIndex=-1,
                                            x=x, y=y, keepRoute=0)
                        traci.vehicle.setSpeed(vehID=object_id, speed=speed)

                    injected_vehicles.add(object_id)
                        
                if object_class == "HUMAN":
                    perceived_persons.append(object_id)
                    # print(object_id, speed)
                    if object_id not in injected_persons:
                        traci.person.add(personID=object_id,edgeID=depart,pos=0)
                        traci.person.setSpeed(object_id,speed)
                        traci.person.appendWaitingStage(object_id,duration=0.1)
                        # laneId = edge+"_0"
                        # arriv_pos = traci.lane.getLength(laneId)
                        # traci.person.appendWalkingStage(personID = object_id, edges=edge,arrivalPos=arriv_pos,speed=speed)
                        # stage1 = traci.person.getStage(object_id)
                        # traci.person.appendStage(object_id,stage1)
                        # print(traci.person.getStage(object_id))
                    else:
                        traci.person.removeStage(object_id,0)
                        traci.person.moveToXY(personID=object_id, edgeID=edge,
                                x=x, y=y, keepRoute=3)
                        laneId = traci.person.getLaneID(object_id)
                        egdeId = traci.lane.getEdgeID(laneId)
                        arriv_pos = traci.lane.getLength(laneId)
                        traci.person.appendWalkingStage(object_id, edges=egdeId,arrivalPos=arriv_pos,speed=speed)
                        traci.person.setSpeed(object_id,speed)
                        

                    # print(traci.person.getSpeed(object_id))
                    
                    injected_persons.add(object_id)


            vehicles_to_remove = [veh_id for veh_id in current_vehicles
                                if veh_id not in perceived_vehicles]

            persons_to_remove = [p_id for p_id in current_persons
                                if p_id not in perceived_persons]


            """
                debug
            """
            # if traci.person.getIDList():
            #     for i in traci.person.getIDList():
            #         print(i,"::","speed::",traci.person.getSpeed(i))
            # print("car::",traci.simulation.getDepartedIDList())
            # print("person::",traci.simulation.getArrivedPersonIDList())
            # print(current_vehicles)
            # print("arrived::",traci.simulation.getArrivedIDList())
            # print(current_persons)
            # print(perceived_vehicles)
            # print(perceived_persons)
            # print(vehicles_to_remove)
            # print(traci.simulation.getTime(),timestamp)

            # try:
                # for veh_id in vehicles_to_remove:
                #     traci.vehicle.remove(veh_id,reason=2)
        
            for p_id in persons_to_remove:
                traci.person.removeStages(p_id)
                try:
                    laneId = traci.person.getLaneID(p_id)
                    if laneId != "":
                        egdeId = traci.lane.getEdgeID(laneId)
                        arriv_pos = traci.lane.getLength(laneId)
                        traci.person.appendWalkingStage(p_id, edges=egdeId,arrivalPos=arriv_pos)
                except:
                    pass


            if (timestamp - lasttimestamp)>1:
                # if traci.simulation.getMinExpectedNumber() > 0:
                lasttimestamp = timestamp
                diff = timestamp - lasttimestamp
                for i in range(diff):
                    traci.simulationStep()
            else:
                # if traci.simulation.getMinExpectedNumber() > 0:
                lasttimestamp = timestamp
                traci.simulationStep()


        print(f"Simulation of file {args.file} completed successfully.")
        traci.close()

    except Exception as e:
        print(e)
        print("Error :(")

    