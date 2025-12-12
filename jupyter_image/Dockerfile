FROM jupyter/scipy-notebook:latest

# Tambah library praktikum kalau perlu, contoh scikit-learn, pandas, dsb.
RUN pip install scikit-learn pandas matplotlib

# Copy modul praktikum ke direktori kerja user
COPY praktikum_ml_iris.ipynb /home/jovyan/work/praktikum_ml_iris.ipynb

# Pastikan kepemilikan file benar
USER root
RUN chown -R 1000:100 /home/jovyan/work
USER $NB_UID
