# needed for file
    # Parse collection_id and dataset_id from filename
    # Create revision for the collection, or else error if there is already exists a revision
    # For each dataset (d) in the revision, obtain association between revision_dataset_id (d['id']) and published_dataset_id  (d['revision_of'])
    # Upload schema 3.0.0 h5ad file from S3 to the revision_id and the specific revision_dataset_id

import argparse
import logging
import os
import pandas as pd
import requests
import subprocess
import sys
import scanpy as sc
import boto3
from botocore.exceptions import ClientError
from src.utils.config import set_api_access_config
from src.utils.logger import set_log_level
from src.collection import get_collection,create_revision
from src.dataset import get_dataset,get_download_links_for_assets,upload_local_datafile, upload_datafile_from_link


def getArgs():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--collection', '-c')
    parser.add_argument('--bucket', '-b')
    parser.add_argument('--production',
                        default=False,
                        action='store_true')
    #parser.add_argument('--dev', '-m')
    args = parser.parse_args()
    return args


def create_presigned_url(bucket_name, object_name, expiration=3600):
    """Generate a presigned URL to share an S3 object

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """

    # Generate a presigned URL for the S3 object
    s3_client = boto3.client('s3')
    try:
        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except ClientError as e:
        logging.error(e)
        return None

    # The response contains the presigned URL
    return response

def get_ids_from_bucket(bucket, collection, original_ids):
    """Get collection id and bucket object name of correct file 

    :param bucket: bucket name 
    :param collection: collection uuid
    :param original_ids: list of unrevised dataset uuids 
    :return: bucket object key
    """
    s3 = boto3.resource('s3')
    bucket = 'submissions-lattice'
    client = boto3.client('s3')
    bucket = s3.Bucket(bucket)
    bucket_key=''
    for bucket_obj in bucket.objects.all():
        if bucket_obj.key.startswith("cxg_migration/Lattice_migration_3.0.0/Public_datasets/") and bucket_obj.key.endswith('.h5ad'):
            bucket_file = str(bucket_obj).split('/')[-1][:-2]
            [coll_id, data_id, lat_id, version] = bucket_file.split('_')
            if coll_id == collection and data_id in original_ids:  
                bucket_key = bucket_obj.key    
                original_ids.remove(data_id)        
            else: print('data collection not there dude')
            
    return bucket_key

def upload_file_from_s3(bucket_key, rev_c_id, rev_d_id):
    """ looks through bucket to find collection that matches collection uuid from argument
    :param collection: collection uuid from S3 bucket
    :param bucket: S3 bucket url
    :return: calls create_presigned_url() to return presigned url of collection in S3 bucket
    """
    presigned_url = create_presigned_url('submissions-lattice', bucket_key, expiration=3600)
    upload_datafile_from_link(presigned_url, rev_c_id, rev_d_id)
    

def main():
    """
    upload files from S3 to cxg portal by creating a revision, obtaining files from s3 bucket submissions-lattice, then uploading to cxg portal
    """
    # obtain api production key
    args = getArgs()
    if args.production:
        set_api_access_config('cxg-api-key.txt')
        print('Working in production')
    else:
        # dont put --production
        set_api_access_config('cxg-api-key-dev.txt', env='dev')
        print('Working in dev')
    
    # obtain collection uuid and bucket url from args
    coll_id = args.collection # coll uuid
    bucket = args.bucket
    print(f'Starting Collection {coll_id}')
    print(f'Bucket url {bucket}')

    #get the Collection and exit if a revision is in progress
    collection = get_collection(coll_id)
    if collection['revising_in']:
        sys.exit('Revision in progress - stopping')
    else:
        #start a revision
        rev_c_id = create_revision(coll_id)
        print(f'Started Revision {rev_c_id}')

    #gather the Dataset IDs from the revision
    revision = get_collection(rev_c_id)
    datasets = [rev_d_id['id'] for rev_d_id in revision['datasets']]
    original_ids = [d_id['revision_of'] for d_id in revision['datasets']] # get dataset uuids to make sure revision matches
    print(str(len(datasets)) + ' Datasets to process')
    
    for rev_d_id in datasets:
        print(f'Starting Dataset {rev_d_id}')
        # upload file from s3 (presigned url)
        # make sure that the data_id matches revision_of ( make if case here)
        
        bucket_key = get_ids_from_bucket(bucket, coll_id, original_ids)
        upload_file_from_s3(bucket_key, rev_c_id, rev_d_id)
        print('done here')
        # catch error, print out message
         
      

if __name__ == '__main__':
    main()
