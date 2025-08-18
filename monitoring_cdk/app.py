#!/usr/bin/env python3
import os

import aws_cdk as cdk

from monitoring_cdk.monitoring_cdk_stack import MonitoringCdkStack


app = cdk.App()
MonitoringCdkStack(app, "MonitoringCdkStack",
    # このスタックは現在のCLI設定のアカウント/リージョンにデプロイされます
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

app.synth()

app.synth()
