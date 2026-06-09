from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer,ProjectSerializer,UserSerializer,UserTaskListSerializer,UserTagListSerializer,EmployeeSerializer
from .models import Employee,User,Project,UserTaskList
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated,AllowAny
from django.conf import settings
from django.core import signing
import boto3
from botocore.exceptions import BotoCoreError, ClientError

VIEWER_USER_TYPE = 4
SHARE_TOKEN_SALT = "inspection-task-share"


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def normalize_project_ids(project_ids):
    if not project_ids:
        return []

    if not isinstance(project_ids, list):
        project_ids = [project_ids]

    normalized_ids = []
    for project_id in project_ids:
        try:
            normalized_ids.append(int(project_id))
        except (TypeError, ValueError):
            continue

    return normalized_ids


def assigned_project_queryset(user):
    project_ids = accessible_project_ids(user)
    if not project_ids:
        return Project.objects.none()

    return Project.objects.filter(id__in=project_ids, isDeleted=False)


def project_descendant_ids(project_ids):
    pending_ids = list(project_ids)
    descendant_ids = set(project_ids)

    while pending_ids:
        child_ids = list(
            Project.objects.filter(parentProject_id__in=pending_ids, isDeleted=False)
            .values_list("id", flat=True)
        )
        new_child_ids = [project_id for project_id in child_ids if project_id not in descendant_ids]
        descendant_ids.update(new_child_ids)
        pending_ids = new_child_ids

    return list(descendant_ids)


def accessible_project_ids(user):
    if user.user_type == 1:
        return list(Project.objects.filter(isDeleted=False).values_list("id", flat=True))

    project_ids = normalize_project_ids(getattr(user, "projectId", None))
    if not project_ids:
        return []

    return project_descendant_ids(project_ids)


def can_access_project(request_user, project):
    if request_user.user_type == 1:
        return True

    return project and project.id in accessible_project_ids(request_user)


def can_view_user_data(request_user, user_id):
    requested_user_ids = normalize_project_ids(user_id)
    return request_user.user_type == 1 or (
        requested_user_ids and requested_user_ids[0] == request_user.id
    )


def can_access_task(request_user, task):
    if request_user.user_type == 1:
        return True

    if not task or not task.project_id:
        return False

    return task.project_id in accessible_project_ids(request_user)


def can_modify_task(request_user, task):
    return request_user.user_type != VIEWER_USER_TYPE and can_access_task(request_user, task)


def can_upload_task(request_user):
    return request_user.user_type != VIEWER_USER_TYPE


def require_super_admin(user):
    return user.user_type == 1



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
        if request.user.user_type == 1:
            project_queryset = Project.objects.filter(isDeleted=False, parentProject__isnull=True)
        else:
            project_queryset = assigned_project_queryset(request.user).filter(parentProject__isnull=True)
        
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
        if request.user.user_type == 1:
            project_queryset = Project.objects.filter(isDeleted=False, parentProject__isnull=True)
        else:
            project_queryset = assigned_project_queryset(request.user).filter(parentProject__isnull=True)
        
        if project_queryset.exists():  # Check if any projects exist
            serializer = ProjectSerializer(project_queryset, many=True)
            return Response({
                "message": "Projects fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({"message": "No projects found."}, status=status.HTTP_404_NOT_FOUND)

        
    def post(self, request):
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can add projects"}, status=status.HTTP_403_FORBIDDEN)

        projectName = request.data.get("projectName") or request.data.get("name")
        parentProjectId = request.data.get("parentProjectId") or request.data.get("parentProject")

        if not projectName:
            return Response({"message": "projectName is required"}, status=status.HTTP_400_BAD_REQUEST)

        parentProject = None
        if parentProjectId:
            parentProject = Project.objects.filter(id=parentProjectId, isDeleted=False).first()
            if not parentProject:
                return Response({"message": "Parent project not found"}, status=status.HTTP_404_NOT_FOUND)

        project = Project.objects.create(name=projectName, parentProject=parentProject)
        
        return Response({
            "message": "Projects Created successfully!",
            "data": ProjectSerializer(project).data,
           
        }, status=status.HTTP_200_OK)
        
        
    def put(self, request):
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can delete projects"}, status=status.HTTP_403_FORBIDDEN)

        projectId = request.data.get("projectId")
        project_ids = project_descendant_ids(normalize_project_ids(projectId))
        Project.objects.filter(id__in=project_ids).update(isDeleted=True)
        
        
        users = User.objects.all()
        for user in users:
            user_project_ids = normalize_project_ids(user.projectId)
            updated_project_ids = [user_project_id for user_project_id in user_project_ids if user_project_id not in project_ids]
            if updated_project_ids != user_project_ids:
                user.projectId = updated_project_ids
                user.save(update_fields=["projectId"])
                
                
        UserTaskList.objects.filter(project_id__in=project_ids).update(project=None)
        UserTaskList.objects.filter(project_id__in=project_ids).update(uploadedUser=None)
      
        
        return Response({
            "message": "Projects Deleted successfully!",
            
        }, status=status.HTTP_200_OK)
        
    
        
     
    
    
    
       
class UserApprovalList(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can view users"}, status=status.HTTP_403_FORBIDDEN)

        user_queryset = User.objects.filter(user_type__in = [2,3,4]).order_by('-createdAt')
        
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
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can update users"}, status=status.HTTP_403_FORBIDDEN)

        userId = request.data.get("userId")
        action = request.data.get("action")
        
        User.objects.filter(id = userId).update(is_active = action)
        

        return Response({
            "message": "updated successfully!",
   
        }, status=status.HTTP_200_OK)
        
        
class AssignProjectToAdmin(APIView):
    permission_classes = [IsAuthenticated,]
    def put(self, request):
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can assign projects"}, status=status.HTTP_403_FORBIDDEN)

        userId = request.data.get("userId")
        projectId = normalize_project_ids(request.data.get("projectId"))
        
        User.objects.filter(id = userId).update(projectId = projectId)
        

        return Response({
            "message": "updated successfully!",
   
        }, status=status.HTTP_200_OK)


class UpdateUser(APIView):
    permission_classes = [IsAuthenticated,]

    def put(self, request):
        if not require_super_admin(request.user):
            return Response({"message": "Only super admin can update users"}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get("userId")
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        full_name = request.data.get("full_name")
        email = request.data.get("email")
        mobile_no = request.data.get("mobile_no")
        user_type = request.data.get("user_type")

        if full_name is not None:
            if not str(full_name).strip():
                return Response({"message": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)
            user.full_name = str(full_name).strip()

        if email is not None:
            email = str(email).strip()
            if not email:
                return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.exclude(id=user.id).filter(email=email).exists():
                return Response({"message": "Email already exists"}, status=status.HTTP_400_BAD_REQUEST)
            user.email = email

        if mobile_no is not None:
            mobile_no = str(mobile_no).strip()
            if not mobile_no:
                return Response({"message": "Mobile number is required"}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.exclude(id=user.id).filter(mobile_no=mobile_no).exists():
                return Response({"message": "Mobile number already exists"}, status=status.HTTP_400_BAD_REQUEST)
            user.mobile_no = mobile_no

        if user_type is not None:
            try:
                user_type = int(user_type)
            except (TypeError, ValueError):
                return Response({"message": "Invalid user type"}, status=status.HTTP_400_BAD_REQUEST)

            if user_type not in [2, 3, 4]:
                return Response({"message": "User type must be Admin, User, or Viewer"}, status=status.HTTP_400_BAD_REQUEST)
            user.user_type = user_type

        user.save()

        return Response({
            "message": "User updated successfully!",
            "data": UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class EmployeeDirectory(APIView):
    permission_classes = [AllowAny,]

    def get(self, request):
        employees = Employee.objects.all()
        serializer = EmployeeSerializer(employees, many=True)

        return Response({
            "message": "Employees fetched successfully!",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = EmployeeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Employee created successfully!",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        employee_id = request.data.get("id")
        employee = Employee.objects.filter(id=employee_id).first()
        if not employee:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = EmployeeSerializer(employee, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Employee updated successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        employee_id = request.data.get("id")
        employee = Employee.objects.filter(id=employee_id).first()
        if not employee:
            return Response({"message": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

        employee.delete()
        return Response({"message": "Employee deleted successfully!"}, status=status.HTTP_200_OK)
        
        
        

class AdminProjectfilter(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        userId = request.GET.get("userId")

        if userId:
            if not can_view_user_data(request.user, userId):
                return Response({"message": "You can only view your assigned projects"}, status=status.HTTP_403_FORBIDDEN)

            userObj = User.objects.filter(id=userId).first()
            if not userObj:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            
            projects = assigned_project_queryset(userObj)
        elif request.user.user_type == 1:
            projects = Project.objects.filter(isDeleted = False)
        else:
            projects = assigned_project_queryset(request.user)

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

        if not can_upload_task(request.user):
            return Response({"error": "Viewer users can only view project data"}, status=status.HTTP_403_FORBIDDEN)

        if not can_view_user_data(request.user, userId):
            return Response({"error": "You can only upload as the logged-in user"}, status=status.HTTP_403_FORBIDDEN)

        userObj = User.objects.filter(id=userId).first()
        if not userObj:
            return Response({"error": "Invalid userId"}, status=status.HTTP_400_BAD_REQUEST)

        projectObj = Project.objects.filter(id=projectId, isDeleted=False).first() if projectId else None
        if not projectObj:
            return Response({"error": "Invalid projectId"}, status=status.HTTP_400_BAD_REQUEST)
        
        if userObj.user_type != 1 and projectObj.id not in accessible_project_ids(userObj):
            return Response({"error": "Project is not assigned to this user"}, status=status.HTTP_403_FORBIDDEN)

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

        if not userTaskObj:
            return Response({"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

        if not can_access_task(request.user, userTaskObj):
            return Response({"message": "You can only view assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserTaskListSerializer(userTaskObj)

        return Response({
                "message": "Data fetched successfully!",
                "data": serializer.data
            }, status=status.HTTP_200_OK)


class CreateTaskShareLink(APIView):
    permission_classes = [IsAuthenticated,]

    def post(self, request):
        taskId = request.data.get("taskId")
        userTaskObj = UserTaskList.objects.filter(id=taskId).first()

        if not userTaskObj:
            return Response({"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

        if not can_access_task(request.user, userTaskObj):
            return Response({"message": "You can only share assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)

        token = signing.dumps({"taskId": userTaskObj.id}, salt=SHARE_TOKEN_SALT)

        return Response({
            "message": "Share token created successfully!",
            "token": token,
        }, status=status.HTTP_200_OK)


class GetSharedTaskDetails(APIView):
    permission_classes = [AllowAny,]

    def get(self, request):
        token = request.GET.get("token")
        taskId = request.GET.get("taskId")

        if token:
            try:
                payload = signing.loads(token, salt=SHARE_TOKEN_SALT)
                taskId = payload.get("taskId")
            except signing.BadSignature:
                return Response({"message": "Invalid share link"}, status=status.HTTP_400_BAD_REQUEST)

        if not taskId:
            return Response({"message": "Share token or taskId is required"}, status=status.HTTP_400_BAD_REQUEST)

        userTaskObj = UserTaskList.objects.filter(id=taskId).first()
        if not userTaskObj:
            return Response({"message": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserTaskListSerializer(userTaskObj)
        data = serializer.data
        readonly_data = {
            "id": data.get("id"),
            "uploadedImage": data.get("uploadedImage"),
            "templateImage": data.get("templateImage"),
            "markTag": data.get("markTag") or [],
            "latLng": data.get("latLng"),
            "createdAt": data.get("createdAt"),
            "project": data.get("project"),
        }

        return Response({
            "message": "Shared task fetched successfully!",
            "data": readonly_data,
        }, status=status.HTTP_200_OK)
        


class GetHomeTask(APIView):
    permission_classes = [IsAuthenticated,]
    def get(self, request):
        projectId = request.GET.get("projectId")
        userId = request.GET.get("userId")

        if projectId:
            project = Project.objects.filter(id=projectId, isDeleted=False).first()
            if not project:
                return Response({"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
            
            if not can_access_project(request.user, project):
                return Response({"message": "Project is not assigned to this user"}, status=status.HTTP_403_FORBIDDEN)

            userTasks = UserTaskList.objects.filter(project=project)
            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        if userId:
            if not can_view_user_data(request.user, userId):
                return Response({"message": "You can only view your own home data"}, status=status.HTTP_403_FORBIDDEN)

            user = User.objects.filter(id=userId).first()
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if user.user_type in [2, 3, 4]:  # assigned projects
                projects = assigned_project_queryset(user)
                userTasks = UserTaskList.objects.filter(project__in=projects)
            else:  # user_type == 1, all projects
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
            project = Project.objects.filter(id=projectId, isDeleted=False).first()
            if not project:
                return Response({"message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

            if not can_access_project(request.user, project):
                return Response({"message": "Project is not assigned to this user"}, status=status.HTTP_403_FORBIDDEN)

            userTasks = UserTaskList.objects.filter(project=project)
            serializer = UserTaskListSerializer(userTasks, many=True)
            return Response({"message": "Data fetched successfully!", "data": serializer.data})

        if userId:
            if not can_view_user_data(request.user, userId):
                return Response({"message": "You can only view your own home data"}, status=status.HTTP_403_FORBIDDEN)

            user = User.objects.filter(id=userId).first()
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if user.user_type in [2, 3, 4]:  # assigned projects
                projects = assigned_project_queryset(user)
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

        if not can_modify_task(request.user, userTaskObj):
            return Response({"error": "You can only update assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)

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
        if not userTaskObj:
            return Response({"error": "Invalid taskId"}, status=status.HTTP_400_BAD_REQUEST)

        if not can_access_task(request.user, userTaskObj):
            return Response({"error": "You can only view assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)



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

        userTaskObj = UserTaskList.objects.filter(id=task_id).first()
        if not userTaskObj:
            return Response({
                "error": "Task not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if not can_modify_task(request.user, userTaskObj):
            return Response({"error": "You can only delete assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)

        userTaskObj.delete()

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

        if not can_modify_task(request.user, userTaskObj):
            return Response({"error": "You can only update assigned project tasks"}, status=status.HTTP_403_FORBIDDEN)

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
