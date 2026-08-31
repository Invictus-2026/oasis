import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib
import os

def train_and_evaluate(dataset_path='oil_types_physical_data.csv', model_output_path='oil_type_rf_model.joblib'):
    print(f"Loading dataset from {dataset_path}...")
    df = pd.read_csv(dataset_path)

    X = df.drop(columns=['oil_type'])
    y = df['oil_type']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print("Training Random Forest model...")
    # Create a pipeline with scaling (good practice even for RF if adding other models later)
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('rf', RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42))
    ])

    pipeline.fit(X_train, y_train)

    print("Evaluating model...")
    y_pred = pipeline.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\nAccuracy: {acc:.4f}\n")
    print("Classification Report:")
    print(classification_report(y_test, y_pred))

    # Feature Importance
    rf_model = pipeline.named_steps['rf']
    importances = rf_model.feature_importances_
    print("Feature Importances:")
    for feature, imp in zip(X.columns, importances):
        print(f"  {feature}: {imp:.4f}")

    joblib.dump(pipeline, model_output_path)
    print(f"\nModel saved successfully to {model_output_path}")

if __name__ == "__main__":
    train_and_evaluate()
