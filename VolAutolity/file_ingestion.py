import argparse
import os
import csv
import tempfile
import pprint
import time
import shutil
# https://learn.microsoft.com/en-us/azure/data-explorer/create-cluster-database?tabs=python#create-an-azure-data-explorer-database
from azure.identity import DefaultAzureCredential
from azure.mgmt.kusto import KustoManagementClient
from azure.mgmt.kusto.models import ReadWriteDatabase
from azure.kusto.ingest import (BlobDescriptor, FileDescriptor, IngestionProperties, IngestionStatus, KustoStreamingIngestClient,
                                ManagedStreamingIngestClient, QueuedIngestClient, StreamDescriptor, ReportLevel, ReportMethod)
from azure.kusto.ingest.status import KustoIngestStatusQueues
from azure.kusto.data import KustoConnectionStringBuilder, KustoClient
from azure.kusto.data.data_format import DataFormat, IngestionMappingKind
from azure.kusto.data.exceptions import KustoServiceError
from azure.kusto.data.helpers import dataframe_from_result_table
# TODO: clean up imports not in use any longer

class AzureDataExplorerFileIngestion:
    def __init__(self, file_path, database, table, tenant_id, client_id, client_secret, cluster_ingestion_uri):
        self.file_path = file_path
        self.database = database
        self.table = table
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.cluster_ingestion_uri = cluster_ingestion_uri
        self.kcsb = KustoConnectionStringBuilder.with_aad_application_key_authentication(
            self.cluster_ingestion_uri, self.client_id, self.client_secret, self.tenant_id)
        self.client = QueuedIngestClient(self.kcsb)

    def ingest_file(self):
        ingestion_props = IngestionProperties(
            database=self.database,
            table=self.table,
            data_format=DataFormat.CSV,
            report_level=ReportLevel.FailuresAndSuccesses,
            additional_properties={'ignoreFirstRecord': 'true'} # change ignore to default to true unless anything else stated?
        )
        file_stats = os.stat(self.file_path)
        file_descriptor = FileDescriptor(self.file_path, file_stats.st_size)
        result = self.client.ingest_from_file(
            file_descriptor, ingestion_properties=ingestion_props)
        print(f"Ingestion result for {self.file_path}: {repr(result)}")

        
    def monitor_ingestion_status(self, max_backoff=30):
        qs = KustoIngestStatusQueues(self.client)
        backoff = 1
        while True:
            if qs.success.is_empty() and qs.failure.is_empty():
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                print(f"No new messages. Backing off for {backoff} seconds")
                continue
            backoff = 1
            success_messages = qs.success.pop(10)
            failure_messages = qs.failure.pop(10)
            pprint.pprint(f"SUCCESS: {success_messages}")
            pprint.pprint(f"FAILURE: {failure_messages}")



def csv_header_cleanup(file_path):
    # Temporary file to hold the modified data
    temp_fd, temp_path = tempfile.mkstemp()
    try:
        with os.fdopen(temp_fd, 'w', newline='', encoding='utf-8') as outfile, \
             open(file_path, mode='r', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            try:
                original_headers = next(reader)
            except StopIteration:
                print(f"File is empty: {file_path}")
                return
            cleaned_headers = [(header.replace('(', '').replace(')', '').replace(' ', '')) for header in original_headers]

            # Write the cleaned headers and the rest of the rows to the temporary file
            writer.writerow(cleaned_headers)
            for row in reader:
                writer.writerow(row)

        # Manually copy the temporary file to the original file path
        shutil.copy(temp_path, file_path)
    finally:
        # Cleanup: Remove the temporary file
        os.remove(temp_path)

def main():
    parser = argparse.ArgumentParser(
        description="Ingest a CSV file into Azure Data Explorer")
    parser.add_argument("--file_path", type=str, required=True,
                        help="Path to the CSV file to ingest")
    parser.add_argument("--database", type=str,
                        required=True, help="Target database name")
    parser.add_argument("--table", type=str, required=True,
                        help="Target table name")
    parser.add_argument("--tenant_id", type=str,
                        required=True, help="Azure tenant ID")
    parser.add_argument("--client_id", type=str,
                        required=True, help="Azure client ID")
    parser.add_argument("--client_secret", type=str,
                        required=True, help="Azure client secret")
    parser.add_argument("--cluster_ingestion_uri", type=str,
                        required=True, help="Cluster ingestion URI")


    args = parser.parse_args()

    adx_file_ingestion = AzureDataExplorerFileIngestion(
        file_path=args.file_path,
        database=args.database,
        table=args.table,
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        client_secret=args.client_secret,
        cluster_ingestion_uri=args.cluster_ingestion_uri,
    )
    csv_header_cleanup(args.file_path)
    adx_file_ingestion.ingest_file()


if __name__ == "__main__":
    main()

# usage: python3 adx_ingester.py --file_path "/path/to/yourfile.csv" --database "YourDatabaseName" --table "YourTableName" --tenant_id "YourTenantId" --client_id "YourClientId" --client_secret "YourClientSecret" --cluster_ingestion_uri "YourClusterIngestionUri"
