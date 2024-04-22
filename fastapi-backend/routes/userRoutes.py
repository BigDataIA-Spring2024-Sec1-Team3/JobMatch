from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.security import OAuth2PasswordBearer
from typing import List
import configparser
import jwt
from connections import aws_connection, mongo_connection
from botocore.exceptions import NoCredentialsError, ClientError


router = APIRouter()

config = configparser.ConfigParser()
config.read('./configuration.properties')

# JWT config
SECRET_KEY = config['auth-api']['SECRET_KEY']
ALGORITHM = config['auth-api']['ALGORITHM']

# OAuth2 password bearer token
tokenUrl = config['password']['tokenUrl']
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=tokenUrl)

# Function to get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=400, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = mongo_connection()
    collection = db[config['MONGODB']["COLLECTION_USER"]]
    user = collection.find_one({"username": username })
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

def mapUserAndFile(user, file_name):
    try:
        db = mongo_connection()
        collection = db[config['MONGODB']["COLLECTION_USER_FILE"]]
        user_file_data = {"userid": user["userid"], "email": user["email"], "file_name": file_name}
        collection.insert_one(user_file_data)
        return True  
    except Exception as e:
        print(f"An error occurred while mapping user and file: {e}")
        return False  
    
# Function to check if file exists in S3 bucket
def check_file_exists(s3, bucket_name, file_name):
    try:
        s3.head_object(Bucket=bucket_name, Key=file_name)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise

# Function to upload file to S3
def upload_to_s3(file, s3, bucket_name, file_name):
        try:
            file_contents = file.read()

            # Check if the file is empty
            if not file_contents:
                return False, "Empty file provided"
            
            # Upload the file contents to S3
            s3.put_object(Bucket=bucket_name, Key=file_name, Body=file_contents)
            # s3.upload_fileobj(file, bucket_name, file_name)
            return True, "File uploaded successfully"
        except FileNotFoundError:
            return False, "File not found"
        except NoCredentialsError:
            return False, "Credentials not found"
            
# Route to handle multiple file uploads
@router.post("/upload/")
async def upload_files_to_s3(files: List[UploadFile] = File(...), current_user: dict = Depends(get_current_user)):
    try:
        s3, bucket_name = aws_connection()
        resumes_folder_name= config['s3-bucket']['resumes_folder_name']
        uploaded_files = []
        for file in files:
            file_name = resumes_folder_name+file.filename
            # Check if the file already exists in S3
            if check_file_exists(s3, bucket_name, file_name):
                # If it exists, skip processing this file and move to the next one
                uploaded_files.append({"file_name": file.filename, "status": "File already exists"})
                continue
            # If the file doesn't exist, upload it to S3
            success, message = upload_to_s3(file.file, s3, bucket_name, file_name)
            s3_file_url = "s3://" + bucket_name + "/" + file_name
            if success:
                if mapUserAndFile(current_user, file.filename):
                    uploaded_files.append({"file_name": file.filename, "file_location": s3_file_url, "status": "File uploaded successfully"})
            else:
                return {"error": message}
        
        return {"message": "Files processed successfully", "uploaded_files": uploaded_files}
    except Exception as e:
        return {"error": str(e)}
    finally:
        for file in files:
            file.file.close()


@router.get("/getJobMatches/")
async def get_job_matches(jobs: List[str], current_user: dict = Depends(get_current_user)):
    print(jobs)

@router.get("/files/", response_model=List[str])
async def get_files(current_user: str = Depends(get_current_user)):
    db = mongo_connection()
    collection = db[config['MONGODB']["COLLECTION_USER_FILE"]]
    email = current_user['email']
    user_files = collection.find({"email": email})
    files = [file["file_name"] for file in user_files]
    print("files", files)
    if not files:
        raise HTTPException(status_code=404, detail="No files found for the user")
    return files