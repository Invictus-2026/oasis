import joblib
import pandas as pd
import os
from typing import Dict, Any

def assess_oil_impact(predicted_type: str, thickness_proxy: float) -> Dict[str, Any]:
    """
    Assesses the environmental (evaporation) and navigational (routing) impact based on the oil type.
    """
    assessment = {
        'evaporation_potential': '',
        'navigational_hazard': '',
        're_route_needed': False
    }

    if predicted_type == 'Petrol':
        assessment['evaporation_potential'] = 'Highly Volatile. Evaporates rapidly (often within hours). Will dissipate naturally.'
        assessment['navigational_hazard'] = 'Thin micro-film forms — low physical obstruction. Oil will be gone before vessel reaches zone.'
        assessment['re_route_needed'] = False

    elif predicted_type == 'Kerosene':
        assessment['evaporation_potential'] = 'Volatile. Evaporates moderately fast, reduced persistence.'
        assessment['navigational_hazard'] = 'Moderate evaporation rate — slick will naturally thin out before causing fouling.'
        assessment['re_route_needed'] = False

    elif predicted_type == 'Diesel':
        assessment['evaporation_potential'] = 'Moderate evaporation. Will leave a persistent residue.'
        assessment['navigational_hazard'] = 'MODERATE HAZARD. Lower fire risk, but can cause mild fouling.'
        assessment['re_route_needed'] = False

    elif predicted_type == 'Light Crude Oil':
        assessment['evaporation_potential'] = 'Slow evaporation. Highly persistent.'
        assessment['navigational_hazard'] = 'LOW TO MODERATE HAZARD. Can foul cooling intakes but generally safe for transit.'
        assessment['re_route_needed'] = False

    elif predicted_type == 'Heavy Crude Oil':
        assessment['evaporation_potential'] = 'Very little evaporation. Emulsifies easily and persists for long periods.'
        if thickness_proxy > 0.5:
            assessment['navigational_hazard'] = 'FOULING HAZARD. Thick layer can severely clog engine cooling water intakes and foul ship hulls.'
            assessment['re_route_needed'] = True
        else:
            assessment['navigational_hazard'] = 'MILD FOULING HAZARD. Proceed with caution to avoid intake clogging.'
            assessment['re_route_needed'] = False
            
    else:
        assessment['evaporation_potential'] = 'Unknown'
        assessment['navigational_hazard'] = 'Unknown'

    return assessment


def predict_oil_type(features_dict, model_path='oil_type_rf_model.joblib'):
    """
    Predicts the oil type based on real-time extracted features from SAR data.
    
    Args:
        features_dict (dict): A dictionary containing the following keys:
            - contrast_dB
            - thickness_proxy
            - area_growth_rate
            - weathering_indicator
            - VV_VH_ratio
        model_path (str): Path to the saved trained model.
        
    Returns:
        str: Predicted oil type (e.g., 'Heavy Crude Oil', 'Petrol')
    """
    
    # Resolve absolute path for the model relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_abs_path = os.path.join(script_dir, model_path)
    
    if not os.path.exists(model_abs_path):
        raise FileNotFoundError(f"Model file not found at {model_abs_path}. Please train the model first.")

    model = joblib.load(model_abs_path)
    
    # Ensure correct feature order as trained
    feature_order = ['contrast_dB', 'thickness_proxy', 'area_growth_rate', 'weathering_indicator', 'VV_VH_ratio']
    
    # Create DataFrame for prediction (handles the pipeline properly)
    df = pd.DataFrame([features_dict], columns=feature_order)
    
    prediction = model.predict(df)[0]
    
    # Assess impact based on the physical features
    impact = assess_oil_impact(prediction, features_dict.get('thickness_proxy', 0))
    
    return {
        'predicted_type': prediction,
        'impact_assessment': impact
    }

if __name__ == "__main__":
    # Test cases
    test_heavy_crude = {
        'contrast_dB': -11.5,
        'thickness_proxy': 0.85,
        'area_growth_rate': 0.08,
        'weathering_indicator': 0.95,
        'VV_VH_ratio': 14.2
    }
    
    test_petrol = {
        'contrast_dB': -2.1,
        'thickness_proxy': 0.015,
        'area_growth_rate': 0.96,
        'weathering_indicator': 0.02,
        'VV_VH_ratio': 2.8
    }

    print(f"Testing features mimicking Heavy Crude...")
    result_hc = predict_oil_type(test_heavy_crude)
    print(f"Prediction: {result_hc['predicted_type']}")
    print(f"Impact: {result_hc['impact_assessment']}")
    
    print("-" * 30)
    
    print(f"Testing features mimicking Petrol/Gasoline...")
    result_p = predict_oil_type(test_petrol)
    print(f"Prediction: {result_p['predicted_type']}")
    print(f"Impact: {result_p['impact_assessment']}")
