### The add-on to calculate the evaluated carbon footprint #######################################

import sys
import os
import glob
import json

total_energy = 0

def find_energy(data):
    if isinstance(data, dict):
        for key, value in data.items():        
            if key == "energy":
                #print("found")
                return float(value)

def find_time(data):
    print("LOL")
    if isinstance(data, dict):
        print("IS")
        for key, value in data.items():
            print(key)        
            if key == "endTime":
                print("Value : ", value)
                return float(value)

def find_component(data, component):
    if isinstance(data, dict):
        for key, value in data.items():        
            if key == component:
                # print("found", component)
                return value

carbon_density = 25.75
carbon_by_weight = 344
use_density = 0.15

def embedded_footprint_evaluation(scenario, total_time) :

    print("total time = ", total_time)

    embedded_carbon = 0

    # Building the path to the "platform-types.json" file
    base_dir = os.path.dirname(os.path.dirname(__file__))
    platform_file = os.path.join(os.path.dirname(base_dir), "data", scenario, "platform-types.json")

    if not os.path.exists(platform_file):
        raise FileNotFoundError(f"{platform_file} file is not to be found. PLease check it.")

    with open (platform_file) as f2:
        data = json.load(f2)
    
        cles = data.keys()
        for component in cles:
            parameters = find_component(data, component)
            lifespan = parameters["lifespan"] * 3600 * 24  *  365.2425
            print ("mass = ", parameters["mass"], flush = True)
            embedded_carbon += carbon_by_weight * parameters["mass"] * total_time / (lifespan * use_density)

    return embedded_carbon

def use_footprint_evaluation(total_energy) :

    # print("total energy = ", total_energy, flush = True)
    use_carbon = total_energy * carbon_density
            #TODO extract th eQoS from the result files

    return use_carbon

def calculation_of_footprint_at_the_end(scenario) :

    # Building the path towards the "result" folder
    base_dir = os.path.dirname(os.path.dirname(__file__))
    ids_dir = os.path.join(os.path.dirname(base_dir), "../../data", scenario)
    result_dir = os.path.join(os.path.dirname(base_dir), "result")
    file_pattern = "*.json"
    
    # Looking for the files with the right pattern
    json_files = glob.glob(os.path.join(result_dir, file_pattern))
    
    if not json_files:
        raise FileNotFoundError(f"No JSON file in {result_dir}.")
    
    # Selecting the youngest
    file = max(json_files, key=os.path.getmtime)
    
    print(f"Used file : {file}", flush = True)
    
    with open(file) as f:
        data = json.load(f)
        total_energy = find_energy(data)
        print("total energy = ", total_energy, flush = True)
        total_time = find_time(data)
        print("total time = ", total_time)

    use_carbon = total_energy * carbon_density

    embedded_carbon = embedded_footprint_evaluation(scenario, total_time)

    return (use_carbon, embedded_carbon)

def calculation_of_footprint(scenario, total_energy, total_time) :

    print("total energy = ", total_energy, flush = True)

    use_carbon = use_footprint_evaluation(total_energy)
    embedded_carbon = embedded_footprint_evaluation(scenario, total_time)

    return (use_carbon, embedded_carbon)

def footprint_evaluation(scenario, energy, time) :

    ### Call to the carbon footprint add-on #########

    try:
        carbon = calculation_of_footprint(scenario, energy, time)
        use_carbon = carbon[0]
        embedded_carbon = carbon[1]
        total_carbon = use_carbon + embedded_carbon
        print("Use carbon =", use_carbon, "\nEmbedded carbon =", embedded_carbon)
        print("Total carbon emissions =", use_carbon + embedded_carbon)

        # Writing in the evaluation result file
        with open("evaluation-result.txt", "w") as f:
            f.write(f"{total_carbon}\n")  # Écrire la première valeur suivie d'un saut de ligne
            f.write(f"QoS\n")
            #TODO extract th eQoS from the result files
    except Exception as e:
        print(f"Error in calculation_of_footprint: {e}", flush = True)

    print(f"Arguments reçus : {sys.argv}", flush=True)

    return total_carbon






if __name__ == "__main__":

    ### Call to the carbon footprint add-on #########

    try:
        carbon = calculation_of_footprint_at_the_end("ids")
        use_carbon = carbon[0]
        embedded_carbon = carbon[1]
        print("Use carbon =", use_carbon, "\nEmbedded carbon =", embedded_carbon)
        print("Total carbon emissions =", use_carbon + embedded_carbon)

        # Writing in the evaluation result file
        with open("evaluation-result.txt", "w") as f:
            f.write(f"{use_carbon + embedded_carbon}\n")  # Écrire la première valeur suivie d'un saut de ligne
            f.write(f"QoS\n")
            #TODO extract th eQoS from the result files
    except Exception as e:
        print(f"Error in calculation_of_ids: {e}", flush = True)

    print(f"Arguments reçus : {sys.argv}", flush=True)
