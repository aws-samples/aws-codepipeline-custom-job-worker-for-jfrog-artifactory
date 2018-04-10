## AWS CodePipeline configuration templates

This directory consists of 2 JSON files that define a pipeline structure.

The file named `source-build-actions-codepipeline.json` creates a AWS CodeCommit 
source action and a AWS CodeBuild build action.

The template named `3-stage-custom-action-codepipeline.json` extends the other 
template by adding a custom action deploy stage that deploys to a custom provider 
called 'Artifactory'.

**Before** using either of those templates, you first need to change some of the 
values to match your use case.

**Before** using the template named `3-stage-custom-action-codepipeline.json`, 
you must first create the Artifactory custom action defined in [this JSON file](../custom-action/artifactory_custom_action_deploy_npm.json) 
by executing the command 

`aws codepipeline create-custom-action-type --cli-input-json file://artifactory_custom_action_deploy.json --region='us-west-2'`

### Using the JSON files to create a pipeline
If you are setting up a pipeline using the `source-build-actions-codepipeline.json` file, 
you need to enter the correct values for your desired pipeline:
- For the `roleArn`, replace `<YOUR-ACCOUNT-NUMBER-HERE>` with your AWS account number, ex. 123456789012.
- In the `Source` stage, under configuration, change the value for "RepositoryName" from `<CODE-REPOSITORY-SOURCE-NAME-HERE>` to the CodeCommit source code repository you will be using for the pipeline.
- In the stage named `CodeBuild`, in the configuration section, change the vaule for "ProjectName" from `<CODEBUILD-PROJECT-NAME>` to the CodeBuild project name you want to use in your pipeline.
- In the `artifactStore` section, for `location`, replace `<AWS-ACCOUNT-NUMBER>` with your AWS account number.
- In the `name` section, replace `<NAME-OF-PIPELINE>` with your desired name of your AWS CodePipeline pipeline.

If you want to create a pipeline using the `3-stage-custom-action-codepipeline.json`, 
after creating your custom action in AWS CodePipeline, you need to edit the JSON file 
to place the correct configuration values for your desired pipeline.

In addition to the changes outlined above for the `source-build-actions-codepipeline.json` file,
you also need to make additional changes. 
All of these changes will be done in the `Deploy` section of the JSON file:
- In the `configuration` section
	- For the `UserName` value, replace `<ARTIFACTORY-USER>` with your Artifactory user name
	- For the `ArtifactoryHost`, replace `<ARTIFACTORY-HOST>` with the URL endpoint of your Artifactory host
	- For the `Password`, replace `<ARTIFACTORY-USER-PASSWORD>` with a password. **NOTE** - I would recommend entering a placeholder value and replace it later with the correct value through the console. This value is defined as secret and will not be reflected in plain-text in the console window.
	- For `EmailAddress`, replace `<YOUR-EMAIL-ADDRESS>` with your email address

Once you have made the necessary changes to the JSON file you want to use to define your pipeline, create the pipeline through the [AWS Command Line Interface (CLI)](https://aws.amazon.com/cli/) with the following command:

`aws codepipeline create-pipeline --cli-input-json file://source-build-actions-codepipeline.json --region 'us-west-2'`

### Using the CloudFormatoni template to create an AWS CodePipeline, AWS CodeBuild, and AWS CodePipline Custom Action, and AWS CodePipeline Custom Worker
Prerequisites for this template:
- Exiting AWS CodeCommit repository containing a Node.js repository. And exmaple can be found in the node-example directory
- An Amazon S3 bucket containing a zip archive of the npm_job_worker.py and requirements.txt in the custom-action directory
- An Amazon S3 bucket to be used for the output artifacts from AWS CodePipeline. Can be the same bucket as above.
- An Artifactory host
- An exiting Amazon VPC. If you need to build a new one, you can use the [AWS VPC QuickStart](https://github.com/aws-quickstart/quickstart-aws-vpc)

This CloudFormation template creates the following resources:
- AWS CodeBuild project
- AWS CodePipeline Custom Action
- AWS CodePipeline
- Amazon EC2 Launch Config and AutoScaling Group for the Custom Worker
- IAM Role for the CodeBuild project, the CodePipeline pipeline, and the EC2 worker

The CodePipleine creates 3 stages - a Source stage configured for the CodeCommit repository, a Build stage configured with the CodeBuild project, and a Deploy stage configured for the Custom Action defined for the Artifactory repository.

The launch configuration for the Custom Worker installs the appropriate packages, pulls the zip archive of the worker code from the S3 bucket, and runs the worker python script that polls the CodePipeline for jobs.
