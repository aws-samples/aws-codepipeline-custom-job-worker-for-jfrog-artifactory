#!/usr/bin/env python

# 
#    Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"). 
#    You may not use this file except in compliance with the License. 
#    A copy of the License is located at
#
#        http://aws.amazon.com/apache2.0/
#
#    or in the "license" file accompanying this file. This file is distributed 
#    on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either 
#    express or implied. See the License for the specific language governing 
#    permissions and limitations under the License.
#

import boto3
import botocore
import requests
import sys
import os
import time
import errno
import zipfile
import uuid
import subprocess
import base64
import ast
import shutil

from botocore.exceptions import ClientError
from boto3.session import Session
import boto.utils

if len(sys.argv) != 2:
    print('Setting Custom Action version to 1')
    sys.argv[1] = 1

CA_VERSION = sys.argv[1]

instance_info = boto.utils.get_instance_identity()
worker_region = instance_info['document']['region']
codepipeline = boto3.client('codepipeline', region_name=worker_region)


def get_bucket_location(bucketName, init_client):
    region = init_client.get_bucket_location(Bucket=bucketName)['LocationConstraint']
    if not region:
        region = 'us-east-1'
    return region


def get_s3_artifact(bucketName, objectKey, ak, sk, st):
    init_s3 = boto3.client('s3')
    region = get_bucket_location(bucketName, init_s3)
    session = Session(aws_access_key_id=ak,
                      aws_secret_access_key=sk,
                      aws_session_token=st
                      )

    s3 = session.resource('s3',
                          region_name=region,
                          config=botocore.client.Config(signature_version='s3v4')
                          )
    filename = '/tmp/' + objectKey
    # Parse the object key - if there is a prefix, then create the directories
    if os.path.dirname(objectKey):
        directory = os.path.dirname(filename)
        print(directory)
        try:
            os.makedirs(directory)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
    bucket = s3.Bucket(bucketName)
    obj = bucket.Object(objectKey)
    try:
        with open(filename, 'wb') as data:
            obj.download_fileobj(data)
    except ClientError as e:
        print('Downloading the object and writing the file to disk raised this error: ' + str(e))
        raise
    return(filename)


def unzip_codepipeline_artifact(artifact):
    # create a new directory in /tmp
    # Move artifact into that
    # Unzip artifact
    rando = uuid.uuid1()
    temp_dir = '/tmp/' + rando.hex
    print(temp_dir)
    try:
        os.makedirs(temp_dir)
        zip_ref = zipfile.ZipFile(artifact, 'r')
        new_place = zip_ref.extractall(temp_dir)
        print(new_place)
        zip_ref.close()
        print(os.listdir(temp_dir))
        return(os.listdir(temp_dir), temp_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            shutil.rmtree(temp_dir)
            raise


def push_to_npm(configuration, artifact_list, temp_dir, jobId):
    hostname = configuration['ArtifactoryHost']
    username = configuration['UserName']
    pwd = configuration['Password']
    reponame = configuration['RepoKey']
    art_type = configuration['TypeOfArtifact']
    url = hostname + '/artifactory/api/' + art_type + '/' + reponame
    print("Putting artifact into NPM repository " + reponame)
    # We want to get a token from Artifactory so we don't save the Username and Password in the .npmrc file: curl -uUSERNAME:PASSWORD -XPOST "http://ARTIFACTORY_HOST/artifactory/api/security/token" -d "username=config['UserName']" -d "scope=member-of-groups:*"
    # setting username and password then encoding
    data = {'username': username, 'scope': 'member-of-groups:*'}
    token_url = hostname + '/artifactory/api/security/token'
    get_token = requests.post(token_url, data=data, auth=(username, pwd))
    token = ast.literal_eval(get_token.text)['access_token']
    up = username + ':' + token
    enc_up = base64.b64encode(up)
    email = configuration['EmailAddress']
    print("Get the home dir for the user running")
    homedir = os.path.expanduser('~')
    npmconfigfile = homedir + '/.npmrc'
    print("Writing npm config file to homedir: " + homedir)
    print("npmconfig file: " + npmconfigfile)
    with open(npmconfigfile, 'w') as config:
        try:
            config.write("_auth = " + enc_up + "\n")
            config.write("email = " + email + "\n")
            config.write("always-auth = true")
        except Exception as e:
            print("Received error when trying to write the NPM config file %s: %s" % (str(npmconfigfile), str(e)))
    print("Changing directory to " + str(temp_dir))
    os.chdir(temp_dir)
    for artifact in artifact_list:
        print("On artifact: " + str(artifact))
        print("Committing to the repo: " + url)
        print("Sending artifact to Artifactory URL: " + url)
        try:
            npm_config = subprocess.call(["npm", "config", "set", "registry", url])
            print("npm config: " + str(npm_config))
            req = subprocess.call(["npm", "publish", "--registry", url])
            print("Return code from npm publish: " + str(req))
            os.remove(npmconfigfile)
            if req != 0:
                err_msg = "npm ERR! Recieved non OK response while sending response to Artifactory. Return code from npm publish: " + str(req)
                signal_failure(jobId, err_msg)
            else:
                signal_success(jobId)
        except requests.exceptions.RequestException as e:
            print req.text
            print("Received an error when trying to commit artifact %s to repository %s: " % (str(artifact), str(configuration['RepoKey']), str(e))) 
            raise
        print(req)
        return req


def push_to_artifact_generic_repo(artifact_list, artifact_directory, configuration, jobId):
    # Send all artifacts to repostitory
    for artifact in artifact_list:
      if os.path.isfile(artifact):
        url = configuration['ArtifactoryHost'] + '/artifactory/' + configuration['RepoKey'] + '/' + artifact
        print("Sending artifact to Artifactory URL: " + url)
        try:
          req = requests.put(url, data=artifact, auth=(configuration['UserName'], configuration['Password']))
          print(req)
          if req.status_code != 201:
            print req.text
            print req.status_code
            err_msg = 'Recieved non 2xx response while sending response to Artifactory.'
            print(err_msg)
            signal_failure(jobId, err_msg)
          else:
            success = signal_success(jobId)  
        except requests.exceptions.RequestException as e:
          print req.text
          print("Received an error when trying to commit artifact %s to repository %s: " % (str(artifact), str(configuration['RepoKey']), str(e))) 
        print(req)
    return req

def signal_failure(jobId, msg):
    print("Signaling failure, reason: %s" % msg)
    try:
        failure = codepipeline.put_job_failure_result(jobId=jobId, failureDetails={'type': 'JobFailed', 'message': msg})
        return failure
    except Exception as e:
        print("Received an error when attempting to put job failure result: %s" % str(e))

def signal_success(jobId):
    print("Signaling success to CodePipeline")
    try:
      success = codepipeline.put_job_success_result(jobId=jobId, currentRevision={'revision': jobId, 'changeIdentifier': jobId}, executionDetails={'summary': 'Thisworkedoutgreat', 'externalExecutionId': 'some_external_id', 'percentComplete': 100})
      return success
    except Exception as e:
      print("Received this error when attempting to put job success result: %s" % str(e))
      raise

def job_acknowledge(jobId, nonce):
    try:
        print('Acknowledging job')
        result = codepipeline.acknowledge_job(jobId=jobId, nonce=nonce)
        print(result)
        return result
    except Exception as e:
        print("Received an error when trying to acknowledge the job: %s" % str(e))
        raise


def grab_job_info(job):
    nonce = job['jobs'][0]['nonce']
    jobId = job['jobs'][0]['id']
    inputBucketName = job['jobs'][0]['data']['inputArtifacts'][0]['location']['s3Location']['bucketName']
    inputObjectKey = job['jobs'][0]['data']['inputArtifacts'][0]['location']['s3Location']['objectKey']
    try:
      outputBucketName = job['jobs'][0]['data']['outputArtifacts'][0]['location']['s3Location']['bucketName']
      outputObjectKey = job['jobs'][0]['data']['outputArtifacts'][0]['location']['s3Location']['objectKey']
    except IndexError as e:
        print('Error getting output Bucket: %s' % str(e))
        print('No output artifacts defined, setting outputBucketName and outputObjectKey to []')
        outputBucketName = []
        outputObjectKey = []
    access_token = job['jobs'][0]['data']['artifactCredentials']['accessKeyId']
    sa_key = job['jobs'][0]['data']['artifactCredentials']['secretAccessKey']
    s_Token = job['jobs'][0]['data']['artifactCredentials']['sessionToken']
    configuration = job['jobs'][0]['data']['actionConfiguration']['configuration']
    return(nonce, jobId, inputBucketName, inputObjectKey, outputBucketName, outputObjectKey, access_token, sa_key, s_Token, configuration)


def poll_for_jobs():
    try:
        jobs = codepipeline.poll_for_jobs(actionTypeId={'category': 'Deploy', 'owner': 'Custom', 'provider': 'Artifactory', 'version': CA_VERSION})
        while not jobs['jobs']:
            print("There are no jobs: " + str(jobs['jobs']))
            time.sleep(10)
            jobs = codepipeline.poll_for_jobs(actionTypeId={'category': 'Deploy', 'owner': 'Custom', 'provider': 'Artifactory', 'version': CA_VERSION})
            if jobs['jobs']:
                print('Found jobs!')
        return(jobs)
    except ClientError as e:
        print("Received an error: %s" % str(e))
        time.sleep(10)


def main():
  # To make the job run constantly
  while True:
    try:
      job = poll_for_jobs()
      nonce, jobId, inputS3, inputObject, outputS3, outputObject, ak, sk, st, config = grab_job_info(job)
      print(nonce, jobId, inputS3, inputObject, outputS3, outputObject)
      acknowledge = job_acknowledge(jobId, nonce)
      print('Acknowledge job returned: ' + str(acknowledge))
      artifact = get_s3_artifact(inputS3, inputObject, ak, sk, st)
      print(artifact)
      artifact_list, temp_dir = unzip_codepipeline_artifact(artifact)
      pkg = config['TypeOfArtifact']
      if pkg == 'npm':
        write = push_to_npm(config, artifact_list, temp_dir, jobId)
        print('Pushed to npm repository: ' + str(write))
      else:
        write = push_to_artifact_generic_repo(artifact_list, temp_dir)
        print('Pushed to generic repository: ' + str(write))
    except Exception as e:
        print(" Received an error: %s" % e)
        raise


if __name__ == '__main__':
    sys.exit(main())
