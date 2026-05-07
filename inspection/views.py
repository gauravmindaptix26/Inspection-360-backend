from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer,ProjectSerializer,UserSerializer,UserTaskListSerializer,UserTagListSerializer
from .models import User,Project,UserTaskList
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated,AllowAny
from django.conf import settings
import boto3
from botocore.exceptions import BotoCoreError, ClientError


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }



class RegisterUser(APIView):
    permission_classes = [AllowAny,] 
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()   # create user
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user).data  # serialize user data

            return Response({
                "message": "User registered successfully!",
                "tokens": tokens,
                "user": user_data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginUser(APIView):
    permission_classes = [AllowAny,] 
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)
        if user:
            tokens = get_tokens_for_user(user)
            user_data = UserSerializer(user).data

            return Response({
                "message": "Login successful!",
                "tokens": tokens,
                "user": user_data
            }, status=status.HTTP_200_OK)

        return Response({"error": "Invalid email or password"}, status=status.HTTP_400_BAD_REQUEST)
    
    
    
class ProjectList(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        project_queryset = Project.objects.filter(isDeleted = False)
        
        if project_queryset.exists():  # Check if any projects exist
            serializer = ProjectSerializer(project_queryset, many=True)
            return Response({
                "message": "Projects fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({"message": "No projects found."}, status=status.HTTP_404_NOT_FOUND)
    
    
class AddProject(APIView):
    permission_classes = [IsAuthenticated,]
    
    def get(self, request):
        project_queryset = Project.objects.filter(isDeleted = False)
        
        if project_queryset.exists():  # Check if any projects exist
            serializer = ProjectSerializer(project_queryset, many=True)
            return Response({
                "message": "Projects fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({"message": "No projects found."}, status=status.HTTP_404_NOT_FOUND)

        
    def post(self, request):
        projectName = request.data.get("projectName")
        project = Project.objects.create(name = projectName)
        
        return Response({
            "message": "Projects Created successfully!",
           
        }, status=status.HTTP_200_OK)
        
        
    def put(self, request):
        projectId = request.data.get("projectId")
        project = Project.objects.filter(id = projectId).update(isDeleted = True)
        
        
        users = User.objects.filter(projectId__contains=[projectId])
        for user in users:
            if user.projectId and projectId in user.projectId:
                user.projectId.remove(projectId)
                user.save(update_fields=["projectId"])
                
                
        UserTaskList.objects.filter(project_id=projectId).update(project=None)
        UserTaskList.objects.filter(project_id=projectId).update(uploadedUser=None)
      
        
        return Response({
            "message": "Projects Deleted successfully!",
            
        }, status=status.HTTP_200_OK)
        
    
        
     
    
    
    
       
class UserApprovalList(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        user_queryset = User.objects.filter(user_type__in = [2,3]).order_by('-createdAt')
        
        if user_queryset.exists():  # Check if any projects exist
            serializer = UserSerializer(user_queryset, many=True)
            return Response({
                "message": "User fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({"message": "No projects found."}, status=status.HTTP_404_NOT_FOUND)
    
    
    
class ActivateUser(APIView):
    permission_classes = [IsAuthenticated,]
    def put(self, request):
        userId = request.data.get("userId")
        action = request.data.get("action")
        
        User.objects.filter(id = userId).update(is_active = action)
        

        return Response({
            "message": "updated successfully!",
   
        }, status=status.HTTP_200_OK)
        
        
class AssignProjectToAdmin(APIView):
    permission_classes = [IsAuthenticated,]
    def put(self, request):
        userId = request.data.get("userId")
        projectId = request.data.get("projectId")
        
        User.objects.filter(id = userId).update(projectId = projectId)
        

        return Response({
            "message": "updated successfully!",
   
        }, status=status.HTTP_200_OK)
        
        
        

class AdminProjectfilter(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        userId = request.GET.get("userId")

        if userId:
            userObj = User.objects.filter(id=userId).first()
            if not userObj:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            
            projectIds = userObj.projectId
            
            if not projectIds:  # handles None, empty list, or empty string
                projects = Project.objects.none()  # return empty queryset
            else:
                projects = Project.objects.filter(id__in=projectIds,isDeleted = False)
        else:
            projects = Project.objects.filter(isDeleted = False)

        # Prepare filter list
        result = [{proj.id: proj.name} for proj in projects]

        return Response({
            "message": "found successfully!",
            "filterList": result
        }, status=status.HTTP_200_OK)

        
    
class UploadTaskImage(APIView):
    permission_classes = [IsAuthenticated,]
    def post(self, request):
        userId = request.data.get("userId")
        projectId = request.data.get("projectId")  # Required if project field is mandatory
        latLng = request.data.get("latLng")
        uploadedImage = request.data.get("uploadedImage")
        templateImage = request.data.get("templateImage")

        userObj = User.objects.filter(id=userId).first()
        if not userObj:
            return Response({"error": "Invalid userId"}, status=status.HTTP_400_BAD_REQUEST)

        projectObj = Project.objects.filter(id=projectId).first() if projectId else None
        if not projectObj:
            return Response({"error": "Invalid projectId"}, status=status.HTTP_400_BAD_REQUEST)

        userTaskObj = UserTaskList.objects.create(
            uploadedImage=uploadedImage,
            templateImage=templateImage,
            latLng=latLng,
            uploadedUser=userObj,
            project=projectObj
        )

        return Response({
            "message": "Created successfully!",
            "taskId": userTaskObj.id
        }, status=status.HTTP_200_OK)

        

class CreateS3UploadUrl(APIView):
    permission_classes = [IsAuthenticated,]

    def post(self, request):
        file_name = request.data.get("fileName")
        content_type = request.data.get("contentType") or "application/octet-stream"

        if not file_name:
            return Response({"error": "fileName is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            return Response({"error": "AWS credentials are not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not settings.AWS_STORAGE_BUCKET_NAME:
            return Response({"error": "AWS bucket is not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        object_key = file_name.replace("\\", "/").split("/")[-1]

        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        try:
            upload_url = s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=300,
            )
        except (BotoCoreError, ClientError) as error:
            return Response({"error": str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        endpoint_url = settings.AWS_S3_ENDPOINT_URL.rstrip("/")
        if endpoint_url:
            file_url = f"{endpoint_url}/{object_key}"
        else:
            file_url = (
                f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3."
                f"{settings.AWS_S3_REGION_NAME}.amazonaws.com/{object_key}"
            )

        return Response(
            {
                "uploadUrl": upload_url,
                "fileUrl": file_url,
                "key": object_key,
            },
            status=status.HTTP_200_OK,
        )

        
    

class GetTaskDetails(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        taskId = request.GET.get("taskId")

     
        userTaskObj = UserTaskList.objects.filter(
            id = taskId
        ).first()

        serializer = UserTaskListSerializer(userTaskObj)

        return Response({
                "message": "Data fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        


class GetHomeTask(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        projectId = request.GET.get("projectId")
        userId = request.GET.get("userId")

        if projectId:
            project = Project.objects.filter(id=projectId).first()
            if not project:
                return Response({"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

            userTasks = UserTaskList.objects.filter(project=project)
            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        if userId:
            user = User.objects.filter(id=userId).first()
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if user.user_type == 2:  # assigned projects
                projects = Project.objects.filter(id__in=user.projectId,isDeleted = False)
                print(projects,"projects")
                userTasks = UserTaskList.objects.filter(project__in=projects)
                print(userTasks,"userTasks")
                
            elif user.user_type == 3:
                userTasks = UserTaskList.objects.filter(uploadedUser=user)
            else:  # user_type == 1, all projects
                print("kjjjjjjjjjjjjjjjj")
                # projects = Project.objects.filter(isDeleted = False)
                userTasks = UserTaskList.objects.all()

            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        return Response({"message": "Provide projectId or userId"}, status=status.HTTP_400_BAD_REQUEST)
              
            
                
class GetUserHomeTask(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        projectId = request.GET.get("projectId")
        userId = request.GET.get("userId")

        if projectId:
            project = Project.objects.filter(id=projectId).first()
            if not project:
                return Response({"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

            userTasks = UserTaskList.objects.filter(project=project)
            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        if userId:
            user = User.objects.filter(id=userId).first()
            print(user.user_type,"user.user_type")
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if user.user_type == 2:  # assigned projects
                projects = Project.objects.filter(id__in=user.projectId,isDeleted = False)
                userTasks = UserTaskList.objects.filter(project__in=projects)
            else:  # user_type == 1, all projects
                # projects = Project.objects.filter(isDeleted = False)
                userTasks = UserTaskList.objects.all()

            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        return Response({"message": "Provide projectId or userId"}, status=status.HTTP_400_BAD_REQUEST)
              
            
                
            
        
        
        
class AddTag(APIView):
    permission_classes = [IsAuthenticated,]
    def post(self, request):
        taskId = request.data.get("taskId")
        newMarkTag = request.data.get("markTag")  # This should be a dict

        userTaskObj = UserTaskList.objects.filter(id=taskId).first()
        if not userTaskObj:
            return Response({"error": "Invalid taskId"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure markTag is a list
        if userTaskObj.markTag is None:
            userTaskObj.markTag = []

        # Append the new tag
        userTaskObj.markTag.append(newMarkTag)
        userTaskObj.save()

        return Response({
            "message": "Updated successfully!",
            
        }, status=status.HTTP_200_OK)
        
        
        
    def get(self, request):
        taskId = request.GET.get("taskId")
 

        userTaskObj = UserTaskList.objects.filter(id=taskId).first()
        print(userTaskObj)
        if not userTaskObj:
            return Response({"error": "Invalid taskId"}, status=status.HTTP_400_BAD_REQUEST)



        serializer = UserTagListSerializer(userTaskObj)

        return Response({
                "message": "Data fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        
        
class DeleteTask(APIView):
    permission_classes = [IsAuthenticated,]

    def delete(self, request):
        task_id = request.data.get("taskId")  # safer than request.POST

        if not task_id:
            return Response({
                "error": "taskId is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = UserTaskList.objects.filter(id=task_id).delete()

        if deleted_count == 0:
            return Response({
                "error": "Task not found."
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "message": "Deleted successfully!"
        }, status=status.HTTP_200_OK)



class DeleteTag(APIView):
    permission_classes = [IsAuthenticated,]

    def post(self, request):
        taskId = request.data.get("taskId")
        lat = request.data.get("lat")
        lng = request.data.get("lng")

        userTaskObj = UserTaskList.objects.filter(id=taskId).first()
        if not userTaskObj:
            return Response({"error": "Invalid taskId"}, status=status.HTTP_400_BAD_REQUEST)

        if not userTaskObj.markTag:
            return Response({"error": "No tags found"}, status=status.HTTP_404_NOT_FOUND)

        # Filter out the tag to delete
        new_tags = [tag for tag in userTaskObj.markTag 
                    if not (str(tag.get("lat")) == str(lat) and str(tag.get("lng")) == str(lng))]

        if len(new_tags) == len(userTaskObj.markTag):
            return Response({"error": "Tag not found"}, status=status.HTTP_404_NOT_FOUND)

        userTaskObj.markTag = new_tags
        userTaskObj.save()

        return Response({
            "message": "Tag deleted successfully!",
            "remainingTags": userTaskObj.markTag
        }, status=status.HTTP_200_OK)




# import io
# import uuid
# import re
# from PIL import Image, UnidentifiedImageError, ExifTags
# import boto3
# from django.conf import settings
# from rest_framework.views import APIView
# from rest_framework.parsers import MultiPartParser, FormParser
# from rest_framework.response import Response
# from rest_framework import status
# from rest_framework.permissions import IsAuthenticated
# from .serializers import UploadImageSerializer

# class UploadInspImageAPIView(APIView):
#     permission_classes = [IsAuthenticated,]
#     parser_classes = [MultiPartParser, FormParser]

#     def post(self, request):
#         serializer = UploadImageSerializer(data=request.data)
#         if serializer.is_valid():
#             image_file = serializer.validated_data['image']

#             # Validate and open the image
#             try:
#                 img = Image.open(image_file)

#                 # Handle EXIF orientation
#                 try:
#                     for orientation in ExifTags.TAGS.keys():
#                         if ExifTags.TAGS[orientation] == 'Orientation':
#                             break
#                     exif = img._getexif()
#                     if exif is not None:
#                         exif_orientation = exif.get(orientation, None)
#                         if exif_orientation == 3:
#                             img = img.rotate(180, expand=True)
#                         elif exif_orientation == 6:
#                             img = img.rotate(270, expand=True)
#                         elif exif_orientation == 8:
#                             img = img.rotate(90, expand=True)
#                 except (AttributeError, KeyError, IndexError, TypeError):
#                     pass  # No EXIF data

#                 img = img.convert('RGB')  # Convert to JPG
#             except UnidentifiedImageError:
#                 return Response(
#                     {"error": "Uploaded file is not a valid image."},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#             # Optional resize: max width 1920px
#             max_width = 1920
#             if img.width > max_width:
#                 ratio = max_width / img.width
#                 new_height = int(img.height * ratio)
#                 img = img.resize((max_width, new_height), Image.ANTIALIAS)

#             # Save to buffer as compressed JPG, strip metadata
#             buffer = io.BytesIO()
#             img.save(buffer, format='JPEG', quality=85, optimize=True)
#             buffer.seek(0)

#             # Generate safe unique filename
#             safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(uuid.uuid4().hex))
#             file_name = f"insp_images/{safe_filename}.jpeg"

#             # Upload to S3
#             s3 = boto3.client(
#                 's3',
#                 aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#                 aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#                 region_name=settings.AWS_S3_REGION_NAME
#             )
#             s3.upload_fileobj(
#                 buffer,
#                 settings.AWS_STORAGE_BUCKET_NAME,
#                 file_name,
#                 ExtraArgs={'ContentType': 'image/jpeg'}
#             )

#             # Return public URL
#             file_url = f"{settings.AWS_S3_ENDPOINT_URL}/{file_name}"
#             return Response({"url": file_url}, status=status.HTTP_200_OK)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
