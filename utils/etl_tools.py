import os
import requests
import pandas as pd

class ETLTools:
    def __init__(self):
        pass

    def extract_load(self,url:str, output_folder:str, format:str):
        """
        This tool extract the data frim API(url) and loads it into the desired location (output_folder).
        Args:
            url(str): The API Endpoint from which it extract data.
            output_folder (str): The folder where the extracted data will be saved.
        Return:
            str: A message indicating SUCCESS
        """
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__),'..'))
        output_folder = os.path.join(project_root, output_folder)
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            filename = os.path.join(output_folder, f"extracted_data.{format}")
            os.makedirs(output_folder, exist_ok= True)

            df = pd.json_normalize(data['results'])
            if format == "csv":
                df.to_csv(filename, index= False)
            elif format == "json":
                df.to_json(filename, orient = "records", lines= True)
            elif format == "parquet":
                df.to_parquet(filename, index=False)
            else:
                return f"unsupported format: {format}"
            return f"Data successfully extracted and save to {filename}"
        
        except requests.exceptions.RequestException as e:
            return f"dailed to extract data: {e}"


    def transform_load_context(self, file_path: str, output_folder: str, output_format:str):
        """ This transform the data from the specific file and loads it into tge desired location (output folder).
        Args:
            file_path(str): The Path to the file containing the data to be transformed.
            output_folder(str): The folder where the transformed data will be saved.
        Return:
            str: A message indication SUCCESS or FALIURE
        """
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension == ".csv":
            df = pd.read_csv(file_path)
        elif file_extension == ".json":
            df = pd.read_json(file_path, lines= True)
        elif file_extension == ".parquet":
            df = pd.read_parquet(file_path)
        else:
            return f"Unsupported File Extension: {file_extension}"

        top_3_rows = str(df.head(3))
        return top_3_rows

    def execute_code(self, code:str):
        """ It'll execute the code and returns the output.

        Args:
            code(str): The code to be executed
        Return:
            str: Output of the code or error messages.
        """
        try:
            exec(code)
            return "Code executed successfully"
        except Exception as e:
            return f"Code failed to execute:{e}"
    
if __name__ == "__main__":
    obj = ETLTools()
    path = '/Users/priyanshusahay/Desktop/UBER AI AGENT/data/extract/extracted_data.csv'
    print(obj.transform_load_context(path))