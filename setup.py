from setuptools import setup, find_packages

setup(
    name="vsam-delta-platform",
    version="1.0.0",
    description="VSAM → Delta Lake Migration Learning Platform",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "streamlit>=1.32.0",
        "pandas>=2.0.0",
    ],
    extras_require={
        "spark": ["pyspark>=3.5.0", "delta-spark>=3.1.0"],
        "dev": ["pytest>=7.4.0", "pytest-cov>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            "vsam-delta=vsam_delta_platform.ui.app:main",
        ],
    },
)
