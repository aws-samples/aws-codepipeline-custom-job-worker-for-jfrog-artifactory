## AWS Codepipeline Custom Job Worker For Jfrog Artifactory

This project walks through integrating JFrog Artifactory with AWS CodePipeline.

This repository contains the code developed for the post on the AWS DevOps blog https://aws.amazon.com/blogs/devops/integrating-jfrog-artifactory-with-aws-codepipeline/

## Project Structure

**Repository:** https://github.com/aws-samples/aws-codepipeline-custom-job-worker-for-jfrog-artifactory 

**/codepipeline-templates:** This directory contains files that can be used to create an initial 2-stage AWS CodePipeline pipeline, a 3-stage AWS CodePipeline pipeline, and an AWS CloudFormation template that will stand up assets needed to build an NPM project and commit them to an Aritfactory NPM repository.

**/custom-action:** This directory contains a json file with the definition of the custom action created to integrate with [JFrog Artifactory](https://jfrog.com/artifactory/)

**/job-worker:** This directory contains the python code that runs within the custom job worker that publishes node.js code to an NPM repository within a JFrog Artifactory

**/node-example:** A test node project 
      
## License

This library is licensed under the Apache 2.0 License. 

