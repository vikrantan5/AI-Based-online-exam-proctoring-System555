# admin_views.py - Admin-specific views
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import (
    Student, ExamPaper, Question, StudentExamAttempt, 
    StudentAnswer, Result, CheatingEvent
)
from django.contrib.auth.models import User
import json
from groq import Groq

# Initialize Groq client
groq_client = Groq(api_key=settings.GROQ_API_KEY)


@staff_member_required(login_url='/admin/login/')
def admin_dashboard_enhanced(request):
    """Enhanced admin dashboard with comprehensive analytics"""
    
    # Get counts
    total_students = Student.objects.count()
    approved_students = Student.objects.filter(approval_status='approved').count()
    pending_approvals = Student.objects.filter(approval_status='pending').count()
    rejected_students = Student.objects.filter(approval_status='rejected').count()
    
    total_exams = ExamPaper.objects.count()
    active_exams = ExamPaper.objects.filter(is_active=True).count()
    
    total_attempts = StudentExamAttempt.objects.count()
    pending_evaluations = StudentExamAttempt.objects.filter(status='submitted').count()
    evaluated_attempts = StudentExamAttempt.objects.filter(status='evaluated').count()
    
    # Upcoming exams
    upcoming_exams = ExamPaper.objects.filter(
        exam_date__gte=timezone.now(),
        is_active=True
    ).order_by('exam_date')[:5]
    
    # Recent submissions needing evaluation
    pending_subjective = StudentExamAttempt.objects.filter(
        status='submitted'
    ).select_related('student', 'exam_paper').order_by('-submitted_at')[:10]
    
    # Students pending approval
    pending_students = Student.objects.filter(
        approval_status='pending'
    ).order_by('-timestamp')[:10]
    
    context = {
        'total_students': total_students,
        'approved_students': approved_students,
        'pending_approvals': pending_approvals,
        'rejected_students': rejected_students,
        'total_exams': total_exams,
        'active_exams': active_exams,
        'total_attempts': total_attempts,
        'pending_evaluations': pending_evaluations,
        'evaluated_attempts': evaluated_attempts,
        'upcoming_exams': upcoming_exams,
        'pending_subjective': pending_subjective,
        'pending_students': pending_students,
    }
    
    return render(request, 'admin/dashboard_enhanced.html', context)


@staff_member_required(login_url='/admin/login/')
def student_approval_list(request):
    """List all students with approval actions"""
    students = Student.objects.all().order_by('-timestamp')
    
    context = {
        'students': students,
    }
    
    return render(request, 'admin/student_approval_list.html', context)


@staff_member_required(login_url='/admin/login/')
def approve_student(request, student_id):
    """Approve a student"""
    student = get_object_or_404(Student, id=student_id)
    
    student.approval_status = 'approved'
    student.approved_by = request.user
    student.approved_at = timezone.now()
    student.save()
    
    messages.success(request, f"Student {student.name} has been approved!")
    return redirect('student_approval_list')


@staff_member_required(login_url='/admin/login/')
def reject_student(request, student_id):
    """Reject a student"""
    student = get_object_or_404(Student, id=student_id)
    
    student.approval_status = 'rejected'
    student.approved_by = request.user
    student.approved_at = timezone.now()
    student.save()
    
    messages.warning(request, f"Student {student.name} has been rejected!")
    return redirect('student_approval_list')


@staff_member_required(login_url='/admin/login/')
def exam_paper_list(request):
    """List all exam papers"""
    exam_papers = ExamPaper.objects.all().order_by('-created_at')
    
    context = {
        'exam_papers': exam_papers,
    }
    
    return render(request, 'admin/exam_paper_list.html', context)


@staff_member_required(login_url='/admin/login/')
def exam_paper_create(request):
    """Create a new exam paper"""
    if request.method == 'POST':
        title = request.POST.get('title')
        subject = request.POST.get('subject')
        description = request.POST.get('description')
        duration_minutes = request.POST.get('duration_minutes')
        exam_date = request.POST.get('exam_date')
        instructions = request.POST.get('instructions')
        total_marks = request.POST.get('total_marks', 0)
        passing_marks = request.POST.get('passing_marks', 0)
        
        exam_paper = ExamPaper.objects.create(
            title=title,
            subject=subject,
            description=description,
            duration_minutes=duration_minutes,
            exam_date=exam_date,
            instructions=instructions,
            total_marks=total_marks,
            passing_marks=passing_marks,
            created_by=request.user
        )
        
        messages.success(request, f"Exam paper '{title}' created successfully!")
        return redirect('exam_paper_detail', exam_id=exam_paper.id)
    
    return render(request, 'admin/exam_paper_create.html')


@staff_member_required(login_url='/admin/login/')
def exam_paper_edit(request, exam_id):
    """Edit an exam paper"""
    exam_paper = get_object_or_404(ExamPaper, id=exam_id)
    
    if request.method == 'POST':
        exam_paper.title = request.POST.get('title')
        exam_paper.subject = request.POST.get('subject')
        exam_paper.description = request.POST.get('description')
        exam_paper.duration_minutes = request.POST.get('duration_minutes')
        exam_paper.exam_date = request.POST.get('exam_date')
        exam_paper.instructions = request.POST.get('instructions')
        exam_paper.total_marks = request.POST.get('total_marks', 0)
        exam_paper.passing_marks = request.POST.get('passing_marks', 0)
        exam_paper.is_active = request.POST.get('is_active') == 'on'
        exam_paper.save()
        
        messages.success(request, f"Exam paper '{exam_paper.title}' updated successfully!")
        return redirect('exam_paper_detail', exam_id=exam_paper.id)
    
    context = {
        'exam_paper': exam_paper,
    }
    
    return render(request, 'admin/exam_paper_edit.html', context)


@staff_member_required(login_url='/admin/login/')
def exam_paper_detail(request, exam_id):
    """View exam paper details with questions"""
    exam_paper = get_object_or_404(ExamPaper, id=exam_id)
    questions = exam_paper.questions.all().order_by('order')
    
    context = {
        'exam_paper': exam_paper,
        'questions': questions,
    }
    
    return render(request, 'admin/exam_paper_detail.html', context)


@staff_member_required(login_url='/admin/login/')
def question_create(request, exam_id):
    """Create a new question for an exam"""
    exam_paper = get_object_or_404(ExamPaper, id=exam_id)
    
    if request.method == 'POST':
        question_type = request.POST.get('question_type')
        question_text = request.POST.get('question_text')
        marks = request.POST.get('marks', 1)
        order = request.POST.get('order', 0)
        
        question = Question(
            exam_paper=exam_paper,
            question_text=question_text,
            question_type=question_type,
            marks=marks,
            order=order
        )
        
        if question_type == 'mcq':
            question.option_a = request.POST.get('option_a')
            question.option_b = request.POST.get('option_b')
            question.option_c = request.POST.get('option_c')
            question.option_d = request.POST.get('option_d')
            question.correct_answer = request.POST.get('correct_answer')
        else:  # subjective
            question.model_answer = request.POST.get('model_answer')
        
        question.save()
        
        # Update total marks
        total_marks = exam_paper.questions.aggregate(Sum('marks'))['marks__sum'] or 0
        exam_paper.total_marks = total_marks
        exam_paper.save()
        
        messages.success(request, "Question added successfully!")
        return redirect('exam_paper_detail', exam_id=exam_id)
    
    # Get next order number
    last_question = exam_paper.questions.order_by('-order').first()
    next_order = (last_question.order + 1) if last_question else 1
    
    context = {
        'exam_paper': exam_paper,
        'next_order': next_order,
    }
    
    return render(request, 'admin/question_create.html', context)


@staff_member_required(login_url='/admin/login/')
def question_edit(request, question_id):
    """Edit a question"""
    question = get_object_or_404(Question, id=question_id)
    exam_paper = question.exam_paper
    
    if request.method == 'POST':
        question.question_text = request.POST.get('question_text')
        question.marks = request.POST.get('marks', 1)
        question.order = request.POST.get('order', 0)
        
        if question.question_type == 'mcq':
            question.option_a = request.POST.get('option_a')
            question.option_b = request.POST.get('option_b')
            question.option_c = request.POST.get('option_c')
            question.option_d = request.POST.get('option_d')
            question.correct_answer = request.POST.get('correct_answer')
        else:
            question.model_answer = request.POST.get('model_answer')
        
        question.save()
        
        # Update total marks
        total_marks = exam_paper.questions.aggregate(Sum('marks'))['marks__sum'] or 0
        exam_paper.total_marks = total_marks
        exam_paper.save()
        
        messages.success(request, "Question updated successfully!")
        return redirect('exam_paper_detail', exam_id=exam_paper.id)
    
    context = {
        'question': question,
        'exam_paper': exam_paper,
    }
    
    return render(request, 'admin/question_edit.html', context)


@staff_member_required(login_url='/admin/login/')
def question_delete(request, question_id):
    """Delete a question"""
    question = get_object_or_404(Question, id=question_id)
    exam_id = question.exam_paper.id
    exam_paper = question.exam_paper
    
    question.delete()
    
    # Update total marks
    total_marks = exam_paper.questions.aggregate(Sum('marks'))['marks__sum'] or 0
    exam_paper.total_marks = total_marks
    exam_paper.save()
    
    messages.success(request, "Question deleted successfully!")
    return redirect('exam_paper_detail', exam_id=exam_id)


@staff_member_required(login_url='/admin/login/')
def pending_evaluations_list(request):
    """List all pending subjective evaluations"""
    pending_attempts = StudentExamAttempt.objects.filter(
        status='submitted'
    ).select_related('student', 'exam_paper').order_by('-submitted_at')
    
    context = {
        'pending_attempts': pending_attempts,
    }
    
    return render(request, 'admin/pending_evaluations_list.html', context)


@staff_member_required(login_url='/admin/login/')
def evaluate_subjective_answers(request, attempt_id):
    """Evaluate subjective answers for a student attempt"""
    attempt = get_object_or_404(StudentExamAttempt, id=attempt_id)
    
    # Get all subjective answers
    subjective_answers = attempt.answers.filter(
        question__question_type='subjective'
    ).select_related('question')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'auto_evaluate':
            # Auto-evaluate using Groq AI
            for answer in subjective_answers:
                if not answer.answer_text:
                    answer.marks_obtained = 0
                    answer.ai_feedback = "No answer provided"
                    answer.save()
                    continue
                
                try:
                    # Call Groq API for evaluation
                    evaluation = evaluate_with_groq(
                        question_text=answer.question.question_text,
                        model_answer=answer.question.model_answer,
                        student_answer=answer.answer_text,
                        max_marks=answer.question.marks
                    )
                    
                    answer.marks_obtained = evaluation['marks']
                    answer.ai_feedback = evaluation['feedback']
                    answer.evaluated_by = request.user
                    answer.evaluated_at = timezone.now()
                    answer.save()
                    
                except Exception as e:
                    answer.ai_feedback = f"Error during AI evaluation: {str(e)}"
                    answer.marks_obtained = 0
                    answer.save()
            
            messages.success(request, "Subjective answers auto-evaluated successfully!")
            
        elif action == 'manual_save':
            # Manual override
            for answer in subjective_answers:
                marks_key = f'marks_{answer.id}'
                feedback_key = f'feedback_{answer.id}'
                
                if marks_key in request.POST:
                    answer.marks_obtained = float(request.POST.get(marks_key, 0))
                    answer.ai_feedback = request.POST.get(feedback_key, '')
                    answer.manually_overridden = True
                    answer.evaluated_by = request.user
                    answer.evaluated_at = timezone.now()
                    answer.save()
            
            messages.success(request, "Manual evaluation saved successfully!")
        
        # Calculate total marks
        total_marks_obtained = attempt.answers.aggregate(Sum('marks_obtained'))['marks_obtained__sum'] or 0
        attempt.total_marks_obtained = total_marks_obtained
        attempt.percentage = (total_marks_obtained / attempt.exam_paper.total_marks * 100) if attempt.exam_paper.total_marks > 0 else 0
        attempt.status = 'evaluated'
        attempt.save()
        
        return redirect('publish_result', attempt_id=attempt.id)
    
    context = {
        'attempt': attempt,
        'subjective_answers': subjective_answers,
    }
    
    return render(request, 'admin/evaluate_subjective_answers.html', context)


def evaluate_with_groq(question_text, model_answer, student_answer, max_marks):
    """Use Groq AI to evaluate subjective answer"""
    
    prompt = f"""You are an expert evaluator. Evaluate the following student's answer and provide marks and feedback.

Question: {question_text}

Model Answer: {model_answer}

Student's Answer: {student_answer}

Maximum Marks: {max_marks}

Provide your evaluation in the following JSON format:
{{
    "marks": <marks out of {max_marks}>,
    "feedback": "<detailed feedback explaining the marks>"
}}

Be fair and consistent. Consider:
1. Correctness and accuracy
2. Completeness of the answer
3. Understanding of concepts
4. Clarity of explanation
"""
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert academic evaluator. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        evaluation = json.loads(result_text)
        
        # Ensure marks don't exceed max_marks
        evaluation['marks'] = min(float(evaluation['marks']), float(max_marks))
        
        return evaluation
        
    except Exception as e:
        # Fallback: give 50% marks if AI fails
        return {
            'marks': max_marks * 0.5,
            'feedback': f"AI evaluation failed: {str(e)}. Assigned 50% marks by default. Please manually review."
        }


@staff_member_required(login_url='/admin/login/')
def publish_result(request, attempt_id):
    """Publish result to student"""
    attempt = get_object_or_404(StudentExamAttempt, id=attempt_id)
    
    if request.method == 'POST':
        remarks = request.POST.get('remarks', '')
        
        # Create or update result
        result, created = Result.objects.get_or_create(
            attempt=attempt,
            defaults={
                'total_marks': attempt.exam_paper.total_marks,
                'marks_obtained': attempt.total_marks_obtained,
                'percentage': attempt.percentage,
                'remarks': remarks,
            }
        )
        
        if not created:
            result.remarks = remarks
            result.marks_obtained = attempt.total_marks_obtained
            result.percentage = attempt.percentage
        
        result.grade = result.calculate_grade()
        result.published = True
        result.published_at = timezone.now()
        result.published_by = request.user
        result.save()
        
        # Send email notification
        send_result_email(attempt.student, attempt, result)
        
        messages.success(request, f"Result published for {attempt.student.name}!")
        return redirect('admin_dashboard_enhanced')
    
    # Calculate all details
    all_answers = attempt.answers.all().select_related('question')
    
    context = {
        'attempt': attempt,
        'all_answers': all_answers,
    }
    
    return render(request, 'admin/publish_result.html', context)


def send_result_email(student, attempt, result):
    """Send result notification email to student"""
    subject = f"Exam Result Published: {attempt.exam_paper.title}"
    
    message = f"""
Dear {student.name},

Your result for {attempt.exam_paper.title} ({attempt.exam_paper.subject}) has been published.

Result Summary:
- Total Marks: {result.total_marks}
- Marks Obtained: {result.marks_obtained}
- Percentage: {result.percentage:.2f}%
- Grade: {result.grade}

{f"Remarks: {result.remarks}" if result.remarks else ""}

Login to your dashboard to view detailed results.

Best regards,
FuturProctor Team
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [student.email],
            fail_silently=False,
        )
        result.email_sent = True
        result.email_sent_at = timezone.now()
        result.save()
    except Exception as e:
        print(f"Error sending email: {e}")


@staff_member_required(login_url='/admin/login/')
def results_management(request):
    """Manage all published and unpublished results"""
    published_results = Result.objects.filter(published=True).select_related(
        'attempt__student', 'attempt__exam_paper'
    ).order_by('-published_at')
    
    unpublished_attempts = StudentExamAttempt.objects.filter(
        status='evaluated',
        result__isnull=True
    ).select_related('student', 'exam_paper').order_by('-submitted_at')
    
    context = {
        'published_results': published_results,
        'unpublished_attempts': unpublished_attempts,
    }
    
    return render(request, 'admin/results_management.html', context)
