from sqlalchemy import Column, Integer, String, Text, Date, DateTime, func
from database import Base

class OrgSettings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    org_name = Column(String, index=True)
    org_logo = Column(String)
    org_contact_info = Column(String)
    org_website = Column(String)
    org_email = Column(String)
    org_phone = Column(String)
    org_description = Column(Text)

class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    date_added = Column(DateTime, default=func.now())
    creation_date = Column(Date)
    poster_image = Column(String)
    relative_file_path = Column(String)
    length_minutes = Column(Integer)
    loop = Column(Integer, default=0) # 0 = no loop, 1 = loop
