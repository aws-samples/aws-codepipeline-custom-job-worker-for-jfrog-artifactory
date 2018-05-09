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

import argparse
import ast
import base64
import boto3
import botocore
import errno
import os
import requests
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from botocore.exceptions import ClientError
from boto3.session import Session
import boto.utils

parser = argparse.ArgumentParser(description='Custom action AWS CodePipeline worker to publish Node.js artifacts to an Artifactory NPM repository')
parser.add_argument("--version", help="Set the custom action version the worker will use. Default is '1'")
args = parser.parse_args()

if len(sys.argv) < 2:
    print('Setting Custom Action version to 1')
    sys.argv.append('1')
CA_VERSION = sys.argv[-1]

instance_info = boto.utils.get_instance_identity()
worker_region = instance_info['document']['region']
codepipeline = boto3.client('codepipeline', region_name=worker_region)

def action_type():
    ActionType = {
        'category': 'Deploy',
        'owner': 'Custom',
        'provider': 'Artifactory',
        'version': CA_VERSION }
    return(ActionType)

def poll_for_jobs():
    try:
        artifactory_action_type = action_type()
        print(artifactory_action_type)
        jobs = codepipeline.poll_for_jobs(actionTypeId=artifactory_action_type)
        while not jobs['jobs']:
            time.sleep(10)
            jobs = codepipeline.poll_for_jobs(actionTypeId=artifactory_action_type)
            if jobs['jobs']:
                print('Job found')
        return jobs['jobs'][0]
    except ClientError as e:
        print("Received an error: %s" % str(e))
        raise

def get_job_info(job):
    nonce = job['nonce']
    jobId = job['id']
    inputBucketName = job['data']['inputArtifacts'][0]['location']['s3Location']['bucketName']
    inputObjectKey = job['data']['inputArtifacts'][0]['location']['s3Location']['objectKey']
    try:
      outputBucketName = job['data']['outputArtifacts'][0]['location']['s3Location']['bucketName']
      outputObjectKey = job['data']['outputArtifacts'][0]['location']['s3Location']['objectKey']
    except IndexError as e:
        print('Error getting output Bucket: %s' % str(e))
        print('No output artifacts defined, setting outputBucketName and outputObjectKey to []')
        outputBucketName = []
        outputObjectKey = []
    access_token = job['data']['artifactCredentials']['accessKeyId']
    sa_key = job['data']['artifactCredentials']['secretAccessKey']
    s_Token = job['data']['artifactCredentials']['sessionToken']
    configuration = job['data']['actionConfiguration']['configuration']
    return(nonce, jobId, inputBucketName, inputObjectKey, outputBucketName, outputObjectKey, access_token, sa_key, s_Token, configuration)


def job_acknowledge(jobId, nonce):
    try:
        print('Acknowledging job for jobId %s' % jobId)
        result = codepipeline.acknowledge_job(jobId=jobId, nonce=nonce)
        return(result)
    except Exception as e:
        print("Received an error when trying to acknowledge the job: %s" % str(e))
        raise


def get_bucket_location(bucketName, init_client):
    region = init_client.get_bucket_location(Bucket=bucketName)['LocationConstraint']
    if not region:
        region = 'us-east-1'
    return(region)


def get_s3_artifact(bucketName, objectKey, ak, sk, st):
    init_s3 = boto3.client('s3')
    region = get_bucket_location(bucketName, init_s3)
    session = Session(aws_access_key_id=ak,
                      aws_secret_access_key=sk,
                      aws_session_token=st)

    s3 = session.resource('s3',
                          region_name=region,
                          config=botocore.client.Config(signature_version='s3v4'))
    try:
        tempdirname = tempfile.mkdtemp()
    except OSError as e:
        print('Could not write temp directory %s' % tempdirname)
        raise
    bucket = s3.Bucket(bucketName)
    obj = bucket.Object(objectKey)
    filename = tempdirname + '/' + objectKey
    try:
        if os.path.dirname(objectKey):
            directory = os.path.dirname(filename)
            os.makedirs(directory)
        print('Downloading the %s object and writing it to disk in %s location' % (objectKey, tempdirname))
        with open(filename, 'wb') as data:
            obj.download_fileobj(data)
    except ClientError as e:
        print('Downloading the object and writing the file to disk raised this error: ' + str(e))
        raise
    return(filename, tempdirname)


def unzip_codepipeline_artifact(artifact, origtmpdir):
    # create a new temp directory
    # Unzip artifact into new directory
    try:
        newtempdir = tempfile.mkdtemp()
        print('Extracting artifact %s into temporary directory %s' % (artifact, newtempdir))
        zip_ref = zipfile.ZipFile(artifact, 'r')
        zip_ref.extractall(newtempdir)
        zip_ref.close()
        shutil.rmtree(origtmpdir)
        return(os.listdir(newtempdir), newtempdir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            shutil.rmtree(newtempdir)
            raise


def gen_artifactory_auth_token(configuration):
    hostname = configuration['ArtifactoryHost']
    username = configuration['UserName']
    pwd = configuration['Password']
    # We want to get a token from Artifactory so we don't save the Username and Password in the .npmrc file: curl -uUSERNAME:PASSWORD -XPOST "http://ARTIFACTORY_HOST/artifactory/api/security/token" -d "username=config['UserName']" -d "scope=member-of-groups:*"
    data = {'username': username, 'scope': 'member-of-groups:*'}
    token_url = hostname + '/artifactory/api/security/token'
    get_token = requests.post(token_url, data=data, auth=(username, pwd))
    token = ast.literal_eval(get_token.text)['access_token']
    return(token, hostname, username)


def create_npmconfig_file(configuration, username, token):
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
            return(npmconfigfile)
        except Exception as e:
            print("Received error when trying to write the NPM config file %s: %s" % (str(npmconfigfile), str(e)))
 

def push_to_npm(configuration, artifact_list, temp_dir, jobId):
    reponame = configuration['RepoKey']
    art_type = configuration['TypeOfArtifact']
    print("Putting artifact into NPM repository " + reponame)
    token, hostname, username = gen_artifactory_auth_token(configuration)
    npmconfigfile = create_npmconfig_file(configuration, username, token)
    url = hostname + '/artifactory/api/' + art_type + '/' + reponame
    print("Changing directory to " + str(temp_dir))
    os.chdir(temp_dir)
    try:
        print("Publishing following files to the repository: %s " % os.listdir(temp_dir))
        print("Sending artifact to Artifactory NPM registry URL: " + url)
        subprocess.call(["npm", "config", "set", "registry", url])
        req = subprocess.call(["npm", "publish", "--registry", url])
        print("Return code from npm publish: " + str(req))
        if req != 0:
            err_msg = "npm ERR! Recieved non OK response while sending response to Artifactory. Return code from npm publish: " + str(req)
            signal_failure(jobId, err_msg)
        else:
            signal_success(jobId)
    except requests.exceptions.RequestException as e:
       print("Received an error when trying to commit artifact %s to repository %s: " % (str(art_type), str(configuration['RepoKey']), str(e)))
       raise
    return(req, npmconfigfile)


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
      success = codepipeline.put_job_success_result(jobId=jobId, currentRevision={'revision': jobId, 'changeIdentifier': jobId}, executionDetails={'summary': 'Job completed successfully', 'percentComplete': 100})
      return success
    except Exception as e:
      print("Received this error when attempting to put job success result: %s" % str(e))
      raise


def cleanup(npmconfigfile, tempdir):
    try:
      os.remove(npmconfigfile)
      shutil.rmtree(tempdir)
      subprocess.call(["npm", "cache", "clean"])
      homedir = os.path.expanduser('~')
      npmcache = homedir + '/.npm'
      shutil.rmtree(npmcache)
    except Exception as e:
      print("Received error when attempting to clean up: %s" % str(e))
      raise


def main():
    while True:
        try:
            job = poll_for_jobs()
            nonce, jobId, inputS3, inputObject, outputS3, outputObject, ak, sk, st, config = get_job_info(job)
            acknowledge = job_acknowledge(jobId, nonce)
            print('Acknowledge job returned: ' + str(acknowledge))
            artifact, tempdirname = get_s3_artifact(inputS3, inputObject, ak, sk, st)
            artifact_list, newtempdir = unzip_codepipeline_artifact(artifact, tempdirname)
            pkg = config['TypeOfArtifact']
            if pkg == 'npm':
                publish_stat, npmconfigname = push_to_npm(config, artifact_list, newtempdir, jobId)
                print('Publishing to repository resulted in the status code: %s' % str(publish_stat))
            cleanup(npmconfigname, newtempdir)
        except Exception as e:
            print(" Received an error: %s" % e)
            raise


if __name__ == '__main__':
    sys.exit(main())
