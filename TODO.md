Conditions
• STAGE 1: Collaboration
This stage includes the following branches: master, develop, feature1, feature2. Ensure that changes are reflected in the
master branch by following the workflow below.

• STAGE 2: Test Automation (DO NOT DO THIS FOR NOW; DO ANYTHING ELSE AND WAIT FOR THE REPO TO BE FULL IN MAIN)
Configure Sonar Cloud https://sonarcloud.io in the private repository and run tests to validate:
• Code quality
• Security
• Code coverage
• Integrity and style
• STAGE 3: What should the repository contain?

├── mlops_pipeline/
│ └── src/
 │ └── Cargar_datos.ipynb (already implemented)
 │ └── comprension_eda.ipynb (already implemented)
 │ └── ft_ engineering.py (already implemented)
 │ └──hueristic_model.py (already implemented PR Not merged yet, check with detached checkout)
 │ └──model_training_evaluation.py
 │ └──model_deploy.py (Deployment will be done as a FastAPI API, with a frontend that allows batch submits and predictions, results and data from preditions will be sent for logs and monitoring into a DB (Heroku Postgres DB) and the API will be deployed as a Heroku eco dyno but using Docker images not traditional procfile builds)
 │ └──model_monitoring.py (as a dash dashboard that compute the metrics and show results)
 └ ── config.json
 ├── database.csv
├── requirements.txt
├── .gitignore
├── readme.md
└── set_up.bat

Load_data.ipynb: This notebook is not normally used in the process of
creating a model, since our data should already be in the DWH or data lake as a result
of a separate process that organizes our information into a table. However, for this
case, a non-production sample dataset in .csv format is used. (For now, load it into the same Heroku Postgres DB)
EDA_Understanding.ipynb (Already implemented): Experimental and exploratory data analysis. This should
result in artifacts stored in an experiment.
ft_engineering.py (Already implemented and merged in PR): Creates the first component of our operational model creation workflow,
from which features are generated and the dataset used to train the
models is returned. It includes the result of: the training and evaluation datasets are generated.
Please create pipelines such as the following.
model_training.ipynb (implemented in `etl_scripts/src/development/`): Trains and evaluates different models. This should result in the
selection of the best model (based on model performance, consistency, and scalability).
The following functions must be used: summarize_classification and build_model.
Use comparative charts for the main models. Summary table.



model_deploy.ipynb: Se toma el mejor modelo desplegado y una imagen que contenga las
librerías y el código para una app que permita disponibilizar dicho objeto y despliega el modelo en
un endpoint que puede utilizarse para predicciones (por batch).
model_evaluation.ipynb: Genera un proceso de evaluación que crea una pestaña de
métricas para conocer el desempeño del modelo desplegado.
model_monitoring.ipynb: Crea el trabajo de monitoreo que trae en una tabla los datos
pasados al endpoint junto con los pronósticos entregados por este y los utiliza, con una
periodicidad definida, para muestrear y obtener métricas que permitan detectar cambios en la
población que puedan afectar el desempeño del modelo. Medida del Datadrift.
