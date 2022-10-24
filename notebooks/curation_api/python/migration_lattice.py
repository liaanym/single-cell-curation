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
    return response

def get_dataset_url(bucket, collection, d_id):
    """Get collection id and bucket object name of correct file 

    :param bucket: bucket name 
    :param collection: unrevised collection uuid
    :param d_id: unrevised dataset uuid 
    :return url: presigned url of S3 bucket object dataset. If dataset not in bucket returns empty string ''
    """    
    url = ''
    for bucket_obj in bucket.objects.all():
        bucket_key = bucket_obj.key
        # obtain files
        if bucket_key.startswith("cxg_migration/Lattice_migration_3.0.0/Public_datasets/") and bucket_key.endswith('.h5ad'):
            bucket_file = str(bucket_obj).split('/')[-1][:-2]
            [coll_id, data_id, lat_id, version] = bucket_file.split('_')
            # generate presigned url of matching dataset
            if coll_id == collection and data_id == d_id:  
                url = create_presigned_url('submissions-lattice', bucket_key, expiration=3600)
    return url
       

def upload_file_from_s3(url, rev_c_id, rev_d_id):
    """ Uploads dataset bucket object to cxg portal 
    
    :param url: presigned url of bucket object
    :param collection: collection uuid from S3 bucket
    :return: calls upload_datafile_from_link() to upload dataset from bucket to cxg
    """
    # check if dataset exists in bucket
    if url != '':
        upload_datafile_from_link(url, rev_c_id, rev_d_id)
    

def main():
    """
    upload files from S3 to cxg portal by creating a revision, obtaining files from s3 bucket
    submissio-lattice, then uploading to cxg portal
    """
    # obtain api production key
    args = getArgs()
    if args.production:
        set_api_access_config('cxg-api-key.txt')
        print('Working in production')
    else:
        set_api_access_config('cxg-api-key-dev.txt', env='dev')
        print('Working in dev')

    # obtain collection uuid and bucket url from args
    coll_id = args.collection # coll uuid
    bucket = args.bucket
    # save files in bucket 
    s3 = boto3.resource('s3')
    bucket_name = 'submissions-lattice'
    client = boto3.client('s3')
    bucket = s3.Bucket(bucket_name)
    
    #get the Collection and exit if a revision is in progress
    print(f'Starting Collection {coll_id}')
    print(f'Bucket url {bucket}')
    
    collection = get_collection(coll_id)
    if collection['revising_in']:
        sys.exit('Revision in progress - stopping')
    else:
        #start a revision
        rev_c_id = create_revision(coll_id)
        print(f'Started Revision {rev_c_id}')

    #gather the Dataset IDs from the revision
    revision = get_collection(rev_c_id)
    datasets = {}
    for rev_d_id in revision['datasets']:
        datasets[rev_d_id['id']] = rev_d_id['revision_of'] # create dictionary of original dataset uuid with corresponding revision uuid
    print(str(len(datasets)) + ' Datasets to process')
   
   # upload file 
    for rev_d in datasets.keys():
        print(f'Starting Dataset {rev_d}')
        d_id = datasets[rev_d]
        url = get_dataset_url(bucket, coll_id, d_id)
        upload_file_from_s3(url, rev_c_id, rev_d)
        
if __name__ == '__main__':
    main()
