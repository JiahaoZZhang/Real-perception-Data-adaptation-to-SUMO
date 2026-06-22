#! /bin/python3
import math
import os
import pandas as pd
import numpy as np 
import json 
import sumolib

# retrieve all csv files
def retrieve_csv_files(directory:str
                       ) -> list:
    try:
        csv_files = sorted([file for file in os.listdir(directory) if file.endswith(".csv")])
        return csv_files
    except FileNotFoundError:
        print(f"The directory '{directory}' does not exist.")
        

# concat all csv files
def read_all_csv(csv_files:list, 
                 path:str,
                 delimiter=";",
                 ) -> pd.DataFrame:
    res = []
    for f in csv_files[:]:
        df = pd.read_csv(path+f,delimiter=delimiter).dropna(subset=['Id','timestamp'])
        # print(df.shape)
        res.append(df)
    df = pd.concat(res, ignore_index=True)
    return df

  
# Select objects from a class based on a defined rate.
# Return the list of filtered object IDs.
def filtrate_object(df:pd.DataFrame, 
                    cls:str="VEHICLE",
                    rate:float=0.5
                    ) -> list:
    df1 = df.groupby(['Id'],dropna=False)
    vehicle_list = []
    for key,val in df1:
        df2 = val.value_counts(['Id','Class'],normalize=True)
        if cls in df2.index.levels[1]:
            if df2[:,cls].values > rate:
                vehicle_list.append(key[0])
    return vehicle_list


# Select objects by ID list
def select_by_id(df:pd.DataFrame,
                 id_list:list
                 ) -> pd.DataFrame:
    if not id_list:
        raise Exception("id list is empty") 
    df_v = [df[df['Id']==i].copy() for i in id_list]
    df_v = pd.concat(df_v)
    return df_v


# get rsu info
def rsu_info(rsu_json:str):
    with open(rsu_json,"r") as f:
        rsu_info = json.load(f)
    lat = rsu_info["geographicalPosition"]["latitude"]
    lon = rsu_info["geographicalPosition"]["longitude"]
    head =  rsu_info["trueHeading"]
    return lat, lon, head


# revision of data position according to RSU(fused) 
# pos -> [x, y]
def rot_data(df:pd.DataFrame,
             heading:float
             ) -> pd.DataFrame:
    
    new_df = df.copy()
    theta = math.radians(heading)
    rotation = np.matrix([[np.sin(theta),np.cos(theta)],
                        [np.cos(theta),-np.sin(theta)]])
    
    rot_df = new_df.loc[:,['positionX','positionY']].dot(rotation)
    new_df['rot_x'] = rot_df.iloc[:,0]
    new_df['rot_y'] = rot_df.iloc[:,1]
    
    return new_df


# filter all vehicles that are not on the road
def on_road(x,y,
            net:sumolib.net,
            radius:float=0.5
            ):
    edges = net.getNeighboringEdges(x, y, radius)
    # pick the closest edge
    if len(edges) > 0:
        distancesAndEdges = sorted([(dist, edge) for edge, dist in edges], key=lambda x:x[0])
        dist, closestEdge = distancesAndEdges[0]
        return (dist, closestEdge) 
    return (None, None)


# select the time series data within a fixed observation period.
# start: minimal perceived duration (n*period)
# stop: maximal perceived duration (n*period)
# period: 1ms
# segmentation for the long period ? 
def data_select_period(df:pd.DataFrame,
                       start:float = 0.,
                       stop:float = 150., #15s
                       scale:float = 100.
                    ):
    """select the time series data within a fixed observation period.

    Args:
        df (pd.DataFrame): Input DataFrame
        start (float, optional): minimal perceived duration (n*period). Defaults to 0..
        stop (float, optional): maximal perceived duration (n*period). Defaults to 150..
        scale: Time scale

    Returns:
        tuple(selected, low, up) : return DataFrames of three intervals
    """
    
    low_list = []
    up_list = []
    v_list = []
    
    for k,v in df.groupby('Id'):
        # There are some duplications, drop duplicated Id at the same time.
        new_v = v.copy().drop_duplicates(['Id','timestamp']).reset_index(drop=True)        
        # round off data for every 100ms which correspond to the sensor collection period
        new_v['ts'] = np.ceil((new_v['timestamp'] - new_v['timestamp'].min())/scale)
        
        if new_v['ts'].max() < start:
            low_list.append(k)
        elif new_v['ts'].max() >= stop:
            up_list.append(k)
        else:
            v_list.append(k)       
        
        # segmentation
    return v_list, low_list, up_list
        


# padding 
def data_padding(df:pd.DataFrame,
                 period_start:int = 0,
                 period_stop:int = 50,
                 scale:float = 100.,
                 pad_method:str = 'pad',
                 pad_columns:list = ['timestamp','positionX','positionY','positionZ','VelX','VelY','VelZ','Vel','rot_x','rot_y','ts'],
                 pad_axis = 0,
                 **kwargs
                 ) -> pd.DataFrame:
    """DataFrame interpolation

    Args:
        df (pd.DataFrame): Input DataFrame
        period_start (int, optional): period start time. Defaults to 0.
        period_stop (int, optional): period end time, if -1, set as the time of the end of sequence. Defaults to 50.
        scale (float, optional): time scale. Defaults to 100..
        pad_method (str, optional): padding method. Defaults to 'pad'.
        pad_columns (list, optional): padding colums. Defaults to ['timestamp','positionX','positionY','positionZ','VelX','VelY','VelZ','Vel','rot_x','rot_y','ts'].
        pad_axis (int, optional): padding axis. Defaults to 0.

    Returns:
        pd.DataFrame: return padded DataFrame
    """
    
    # template_v = pd.DataFrame().reindex_like(df[:1])
    v_list = []
    for _,v in df.groupby('Id'):
        new_v = v.copy().sort_values(by=['SUMO TIME'])
        
        # Filter abnormal data (focus on speed, < +3*std, > -3*std)
        # c1 = new_v['VelX'].mean() + 3*new_v['VelX'].std()
        # c2 = new_v['VelX'].mean() - 3*new_v['VelX'].std()
        # c1 = new_v['VelX'] < c1
        # c2 = new_v['VelX'] > c2

        # c3 = new_v['VelY'].mean() + 3*new_v['VelY'].std()
        # c4 = new_v['VelY'].mean() - 3*new_v['VelY'].std()
        # c3 = new_v['VelY'] < c3
        # c4 = new_v['VelY'] > c4
        # new_v = new_v[c1 & c2 & c3 & c4]
        
        
        new_v['ts'] = np.ceil((new_v['SUMO TIME'] - new_v['SUMO TIME'].min())/scale)
        # add NaN padding for a fixed period 
        # if period_stop == -1, correspond the max lifetime length
        if period_stop == -1:
            period_stop_f = int(new_v['ts'].max())
            # print(period_stop_f)
        else:
            period_stop_f = period_stop
            
        new_v = new_v.drop_duplicates(['ts']).set_index(['ts'],drop=False).reindex(range(period_start,period_stop_f))
        
        # use pd.DataFrame.interpolate() method ? 
        # depend on the model, how we imterpolate the value
        # pad_columns = ['timestamp','positionX','positionY','positionZ','VelX','VelY','VelZ','Vel','rot_x','rot_y','ts']
        
        new_v[pad_columns] = new_v[pad_columns].infer_objects(copy=False).interpolate(method=pad_method,order=2, limit_direction='forward', axis=pad_axis)
        tmp_v = new_v.dropna(how='all').drop_duplicates(['SUMO TIME']).copy()
        
        if not tmp_v.empty:
            v_list.append(tmp_v)
        
    res = pd.concat(v_list, ignore_index=True)  
    
    return res