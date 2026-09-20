import psycopg2
from psycopg2 import sql

class DatabaseUtil:
    def __init__(self, db_config):
        self.db_config = db_config
        try:
            self.connection = psycopg2.connect(**db_config)
        except Exception as e:
            print(f"Error connecting to the Database: {e}")
            self.connection = None

    def schema_details(self, schema_name):
        try:
            schema_info_context = ""
            connection = self.connection
            cursor =connection.cursor()
            schema_info_context = f"Database name {schema_name}\n"
            cursor.execute("SELECT table_name from information_schema.tables where table_schema = %s;", (schema_name,))
            tables_list =cursor.fetchall()
            for i in tables_list:
                table_name = i[0]
                schema_info_context = f"{schema_info_context}\nTable: {table_name}\n"
                cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s;", (table_name,))
                column_list =cursor.fetchall()
                for j in column_list:
                    column_name = j[0]
                    data_type = j[1]
                    schema_info_context = f"{schema_info_context}  Column: {column_name}, Type: {data_type}\n"

                # ADDING DUMMY DATA FOR LLM MODEL TO GENERATE QUERY
                cursor.execute(f"SELECT * FROM {schema_name}.{table_name} LIMIT 5;")
                sample_data = cursor.fetchall()
                schema_info_context = f"{schema_info_context} Sample Data\n"
                for k in sample_data:
                    schema_info_context = f"{schema_info_context}   {k}\n"

            return schema_info_context


        except Exception as e:
            print(f"Error connecting to the Database: {e}")
            schema_info_context = f"Error fetching schema details: {e}\n"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

obj = DatabaseUtil({
    "host":"localhost",
    "port":5432,
    "user":"postgres",
    "password":"Priyan@sahay2002",
    "dbname":"postgres"
})

res =obj.schema_details("public")
with open("test_schama.txt", "w") as f:
    f.write(res)

