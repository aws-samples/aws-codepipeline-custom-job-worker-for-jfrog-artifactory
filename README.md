## AWS Codepipeline Custom Job Worker For Jfrog Artifactory

This project walks through integrating JFrog Artifactory with AWS CodePipeline

### Publishing a Node project

The code to set up the Custom Action and Worker for an NPM repository is in: 

https://github.com/aws-samples/aws-codepipeline-custom-job-worker-for-jfrog-artifactory 

in the `custom-action` directory. 

The test Node project is in the `node-example` directory.

For the CodePipeline pipeline to be triggered off of a change in `node-example` codebase, move the contents of `node-example` to a new Git repository and set that as the source of the CodePipeline pipeline.

I set up a CodePipeline that consists of:
- Source: CodeCommit - triggered when anything is committed to the `node-example` repository
- Build: CodeBuild - runs the `npm install` for the package
- Deploy: Artifactory - job worker looks for jobs and run the npm publish to bundle the node package and sends to the Artifactory NPM repository

The custom worker does the following:
- polls for jobs with the category: 'Deploy', the owner: 'Custom', the provider: 'Artifactory', and version: '1'
- once the job is found, acknowledges that it found the job
- grabs the output artifact from the CodeBuild job from S3
- creates a directory in the /tmp/ directory with a random hex name, puts the S3 zip artifact into that directory
- unzips that artifact in the temporary directory
- looks at the TypeOfArtifact, if is 'npm':
	- uses provided username and password to get a temporary access token from JFrog Artifactory
	- encodes the username and token
	- writes the encoded username/token and email address to ~/.npmrc
	- runs `npm config set registry` to point to the Artifactory host
	- runs `npm publish --registry` to bundle the node package and publishes to the Artifactory NPM registy
- if gets a good return code from npm, will signal success to CodePipeline, otherwise it will signal failure

### Set up the custom action in CodePipeline
- the version is set to '1' for testing purposes
- the 'provider' is Artifactory

Configuration for the custom action:
- TypeOfArtifact: this should be set to 'npm'
- RepoKey: this is the name of the repository that you want to commit to, ex. npm
- Username: Artifactory username
- Password: Artifactory password
- Email address: user email address __NOTE__: npm publish will not work if email is not entered here
- ArtifactoryHost: This is the public address of the host where Artifactory is running, ex. https://myexamplehost.com

Set up the custom action using the `artifactory_custom_action_deploy_npm.json` file:

`aws codepipeline create-custom-action-type --cli-input-json file://artifactory_custom_action_deploy_npm.json --region='us-west-2'` 

### The CodePipeline worker
The worker runs on an EC2 instance.
1. Spin up an small EC2 instance.
2. To install the Node Package Manager (NPM) on to your worker, run the following commands:

__on the EC2 instance__

`sudo yum update -y`

`sudo yum install nodejs npm --enablerepo=epel`

3. To ensure that the correct python libraries are available for the worker, copy the file 'requirements.txt' into the EC2 instance and install the packages:

__on your desk top or laptop where the repository exists__

`scp reqirements.txt ec2-user@<WORKER EC2 HOSTNAME or PUBLIC IP>`

__on the EC2 instance__

`pip install -r requirements.txt`

4. Put the `npm_job_worker.py` on the host and run it:

__on your desk top or laptop where the repository exists__

`scp npm_job_worker.py ec2-user@<WORKER EC2 HOSTNAME or PUBLIC IP>`

__on the EC2 instance__

`python npm_job_worker.py &`

So now, the worker is polling for jobs with the category: __'Deploy'__, the owner: __'Custom'__, the provider: __'Artifactory'__, and version: __'1'__

## License

This library is licensed under the Apache 2.0 License. 

