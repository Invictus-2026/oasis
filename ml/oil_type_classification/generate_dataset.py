import pandas as pd
import numpy as np
import os

def generate_physical_dataset(num_samples_per_class=1000, output_path='oil_types_physical_data.csv'):
    """
    Generates a synthetic dataset grounded in physical properties of different oil types.
    Properties are simulated using normal distributions around known relative physical traits.
    """
    np.random.seed(42)
    
    # Define the oil types and their physical parameter distributions (mean, std_dev)
    # Features: ['contrast_dB', 'thickness_proxy', 'area_growth_rate', 'weathering_indicator', 'VV_VH_ratio']
    
    oil_classes = {
        'Heavy Crude Oil': {
            'contrast_dB': (-12.0, 1.5),         # Highly dampens Bragg waves
            'thickness_proxy': (0.8, 0.1),       # Thick layers, high viscosity
            'area_growth_rate': (0.1, 0.05),     # Spreads very slowly
            'weathering_indicator': (0.9, 0.05), # Emulsifies, high persistence
            'VV_VH_ratio': (15.0, 2.0)           # Higher ratio due to dielectric/thickness properties
        },
        'Light Crude Oil': {
            'contrast_dB': (-9.0, 1.2),
            'thickness_proxy': (0.5, 0.1),
            'area_growth_rate': (0.3, 0.1),
            'weathering_indicator': (0.7, 0.1),
            'VV_VH_ratio': (12.0, 1.5)
        },
        'Diesel': {
            'contrast_dB': (-6.0, 1.0),
            'thickness_proxy': (0.2, 0.05),
            'area_growth_rate': (0.6, 0.1),
            'weathering_indicator': (0.4, 0.1),
            'VV_VH_ratio': (8.0, 1.2)
        },
        'Kerosene': {
            'contrast_dB': (-4.0, 0.8),          # Less dampening
            'thickness_proxy': (0.05, 0.02),     # Thin film
            'area_growth_rate': (0.85, 0.05),    # Fast spread
            'weathering_indicator': (0.2, 0.05), # High volatility
            'VV_VH_ratio': (5.0, 1.0)
        },
        'Petrol': {
            'contrast_dB': (-2.5, 0.5),          # Minimum dampening
            'thickness_proxy': (0.01, 0.005),    # Micro-thin film
            'area_growth_rate': (0.95, 0.02),    # Maximum spread
            'weathering_indicator': (0.05, 0.02),# Extreme volatility (rapid evaporation)
            'VV_VH_ratio': (3.0, 0.5)
        }
    }

    data = []
    
    for oil_type, properties in oil_classes.items():
        for _ in range(num_samples_per_class):
            sample = {'oil_type': oil_type}
            for feature, (mean, std) in properties.items():
                # Generate value and ensure physical constraints (e.g., rates/thickness > 0)
                val = np.random.normal(mean, std)
                
                if feature in ['thickness_proxy', 'area_growth_rate', 'weathering_indicator', 'VV_VH_ratio']:
                    val = max(0.001, val) # Cannot be negative
                if feature in ['area_growth_rate', 'weathering_indicator']:
                    val = min(1.0, val)   # Typically normalized between 0 and 1
                    
                sample[feature] = val
            data.append(sample)

    df = pd.DataFrame(data)
    
    # Save the dataset
    df.to_csv(output_path, index=False)
    print(f"Dataset successfully generated with {len(df)} samples and saved to {output_path}")
    
    return df

if __name__ == "__main__":
    generate_physical_dataset(num_samples_per_class=1500)
