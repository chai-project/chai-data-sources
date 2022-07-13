from setuptools import setup

setup(
    name="chai-data-sources",
    packages=["chai_data_sources"],
    version="0.9.0",
    description="Access the Efergy and Netatmo API to interface with the energy meter, thermostat, "
                "and thermostatic values.",
    author="Kim Bauters",
    author_email="kim.bauters@bristol.ac.uk",
    license="Protected",
    install_requires=["pendulum",  # handle datetime instances with ease
                      "requests",  # handle, and mock, API requests
                      "dacite",  # convert dictionaries to dataclass instances
                      "requests-mock",  # test code using requests in a reliable and repeatable way
                      "orjson",  # fast(est) JSON encoder and decoder
                      ],
    classifiers=[],
    include_package_data=True,
    platforms="any",
)
